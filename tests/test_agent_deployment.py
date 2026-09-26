import json
import tempfile
import unittest
from pathlib import Path

from scripts.create_agent import (
    STATE_PATH,
    cleanup_recorded_resources,
    finalize_deployment,
    load_state,
    prompt_agent_options,
    provision_resources,
    provision_update,
    required_config,
    reusable_files,
    save_state,
    state_path,
    updated_state,
)


class FakeFiles:
    def __init__(self, fail_on: int | None = None, delete_failures=None):
        self.fail_on = fail_on
        self.delete_failures = delete_failures or {}
        self.created: list[str] = []
        self.deleted: list[str] = []

    def create(self, *, purpose, file):
        if self.fail_on is not None and len(self.created) + 1 == self.fail_on:
            raise RuntimeError("upload failed")
        file_id = f"file-{len(self.created) + 1}"
        self.created.append(file_id)
        return type("Uploaded", (), {"id": file_id})()

    def delete(self, file_id):
        self.deleted.append(file_id)
        if file_id in self.delete_failures:
            raise self.delete_failures[file_id]


class FakeOpenAI:
    def __init__(self, fail_on: int | None = None, delete_failures=None):
        self.files = FakeFiles(fail_on, delete_failures)


class FakeAgents:
    def __init__(self, delete_failure=None):
        self.deleted: list[tuple[str, str]] = []
        self.delete_failure = delete_failure

    def delete_version(self, *, agent_name, agent_version):
        self.deleted.append((agent_name, agent_version))
        if self.delete_failure is not None:
            raise self.delete_failure


class FakeProject:
    def __init__(self, delete_failure=None):
        self.agents = FakeAgents(delete_failure)


class ConfigTests(unittest.TestCase):
    def test_requires_existing_environment_names(self):
        with self.assertRaisesRegex(ValueError, "FOUNDRY_PROJECT_ENDPOINT"):
            required_config({})

    def test_accepts_the_approved_model(self):
        config = required_config(
            {
                "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/project",
                "FOUNDRY_MODEL_DEPLOYMENT": "gpt-5-mini",
                "FOUNDRY_AGENT_NAME": "manufacturing-agent",
            }
        )
        self.assertEqual(config["agent_name"], "manufacturing-agent")

    def test_rejects_a_different_model(self):
        with self.assertRaisesRegex(ValueError, "gpt-5-mini"):
            required_config(
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/project",
                    "FOUNDRY_MODEL_DEPLOYMENT": "other-model",
                    "FOUNDRY_AGENT_NAME": "manufacturing-agent",
                }
            )

    def base_environ(self, **overrides):
        environ = {
            "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/project",
            "FOUNDRY_MODEL_DEPLOYMENT": "gpt-5-mini",
            "FOUNDRY_AGENT_NAME": "manufacturing-agent",
        }
        environ.update(overrides)
        return environ

    def test_reasoning_effort_defaults_to_medium(self):
        self.assertEqual(required_config(self.base_environ())["reasoning_effort"], "medium")

    def test_accepts_gpt_6_luna_with_xhigh_or_max_reasoning(self):
        for effort in ("xhigh", "max"):
            config = required_config(
                self.base_environ(
                    FOUNDRY_MODEL_DEPLOYMENT="gpt-6-luna", FOUNDRY_REASONING_EFFORT=effort
                )
            )
            self.assertEqual(config["model_deployment"], "gpt-6-luna")
            self.assertEqual(config["reasoning_effort"], effort)

    def test_rejects_unknown_reasoning_effort(self):
        with self.assertRaisesRegex(ValueError, "FOUNDRY_REASONING_EFFORT"):
            required_config(self.base_environ(FOUNDRY_REASONING_EFFORT="extreme"))

    def test_max_reasoning_requires_a_gpt_6_model(self):
        with self.assertRaisesRegex(ValueError, "max"):
            required_config(self.base_environ(FOUNDRY_REASONING_EFFORT="max"))

    def test_state_path_defaults_and_can_be_overridden(self):
        self.assertEqual(state_path(self.base_environ()), STATE_PATH)
        trial = state_path(self.base_environ(FOUNDRY_STATE_FILE=".foundry/trial-state.json"))
        self.assertEqual(trial.name, "trial-state.json")
        self.assertNotEqual(trial, STATE_PATH)

    def test_prompt_agent_uses_medium_reasoning_without_sampling_temperature(self):
        options = prompt_agent_options("gpt-5-mini", "instructions", ["tool"])

        self.assertEqual(options["reasoning"], {"effort": "medium"})
        self.assertEqual(options["text"], {"verbosity": "low"})
        self.assertNotIn("temperature", options)
        self.assertEqual(options["model"], "gpt-5-mini")

    def test_prompt_agent_passes_configured_reasoning_effort(self):
        options = prompt_agent_options(
            "gpt-6-luna", "instructions", ["tool"], reasoning_effort="xhigh"
        )

        self.assertEqual(options["reasoning"], {"effort": "xhigh"})


class StateTests(unittest.TestCase):
    def test_state_round_trip_is_atomic_and_non_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".foundry/state.json"
            state = {"agent_name": "agent", "agent_version": "1", "file_ids": ["f1"]}

            save_state(path, state)

            self.assertEqual(load_state(path), state)
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_missing_state_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(load_state(Path(directory) / "missing.json"))


class ProvisionTests(unittest.TestCase):
    def make_files(self, root: Path, count: int) -> list[Path]:
        paths = []
        for index in range(count):
            path = root / f"file-{index}.csv"
            path.write_text("id\n1\n", encoding="utf-8")
            paths.append(path)
        return paths

    def test_upload_failure_deletes_files_from_that_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            openai = FakeOpenAI(fail_on=3)
            paths = self.make_files(Path(directory), 4)

            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                provision_resources(openai, paths, lambda _: None)

            self.assertEqual(openai.files.deleted, ["file-1", "file-2"])

    def test_agent_creation_failure_deletes_all_uploaded_files(self):
        with tempfile.TemporaryDirectory() as directory:
            openai = FakeOpenAI()
            paths = self.make_files(Path(directory), 2)

            def fail(_):
                raise RuntimeError("agent failed")

            with self.assertRaisesRegex(RuntimeError, "agent failed"):
                provision_resources(openai, paths, fail)

            self.assertEqual(openai.files.deleted, ["file-1", "file-2"])

    def test_success_returns_agent_and_file_ids_without_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            openai = FakeOpenAI()
            paths = self.make_files(Path(directory), 2)
            agent = object()

            actual_agent, file_ids = provision_resources(openai, paths, lambda _: agent)

            self.assertIs(actual_agent, agent)
            self.assertEqual(file_ids, ["file-1", "file-2"])
            self.assertEqual(openai.files.deleted, [])


class CleanupTests(unittest.TestCase):
    def test_cleanup_deletes_only_recorded_version_and_files(self):
        project = FakeProject()
        openai = FakeOpenAI()
        state = {
            "agent_name": "manufacturing-agent",
            "agent_version": "3",
            "file_ids": ["file-a", "file-b"],
        }

        cleanup_recorded_resources(project, openai, state)

        self.assertEqual(project.agents.deleted, [("manufacturing-agent", "3")])
        self.assertEqual(openai.files.deleted, ["file-a", "file-b"])

    def test_cleanup_attempts_every_resource_and_reports_failures(self):
        project = FakeProject(delete_failure=RuntimeError("agent failed"))
        openai = FakeOpenAI(delete_failures={"file-a": RuntimeError("file failed")})
        state = {
            "agent_name": "manufacturing-agent",
            "agent_version": "3",
            "file_ids": ["file-a", "file-b"],
        }

        with self.assertRaisesRegex(RuntimeError, "agent failed.*file failed"):
            cleanup_recorded_resources(project, openai, state)

        self.assertEqual(openai.files.deleted, ["file-a", "file-b"])

    def test_cleanup_tolerates_already_deleted_resources(self):
        class NotFoundError(Exception):
            status_code = 404

        project = FakeProject(delete_failure=NotFoundError())
        openai = FakeOpenAI(delete_failures={"file-a": NotFoundError()})
        state = {
            "agent_name": "manufacturing-agent",
            "agent_version": "3",
            "file_ids": ["file-a"],
        }

        cleanup_recorded_resources(project, openai, state)

    def test_state_write_failure_rolls_back_new_resources(self):
        project = FakeProject()
        openai = FakeOpenAI()
        new_state = {
            "agent_name": "manufacturing-agent",
            "agent_version": "4",
            "file_ids": ["new-file"],
        }

        def fail_save(_path, _state):
            raise OSError("state write failed")

        with self.assertRaisesRegex(OSError, "state write failed"):
            finalize_deployment(
                project,
                openai,
                new_state,
                previous=None,
                state_path=Path("state.json"),
                save=fail_save,
            )

        self.assertEqual(project.agents.deleted, [("manufacturing-agent", "4")])
        self.assertEqual(openai.files.deleted, ["new-file"])


class UpdateTests(unittest.TestCase):
    def make_paths(self, root: Path, names: list[str]) -> list[Path]:
        paths = []
        for name in names:
            path = root / name
            path.write_text("x", encoding="utf-8")
            paths.append(path)
        return paths

    def test_reuses_recorded_files_and_uploads_only_refreshed_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            openai = FakeOpenAI()
            paths = self.make_paths(Path(directory), ["fact_sales.csv", "analysis_helper.py", "late_order_risk.csv"])
            received = []

            agent, file_ids, uploaded = provision_update(
                openai,
                paths,
                {"fact_sales.csv": "old-sales", "late_order_risk.csv": "old-risk"},
                lambda ids: received.append(ids) or "agent",
            )

            self.assertEqual(agent, "agent")
            self.assertEqual(file_ids, ["old-sales", "file-1", "old-risk"])
            self.assertEqual(received, [file_ids])
            self.assertEqual(uploaded, ["file-1"])

    def test_update_failure_deletes_only_new_uploads(self):
        with tempfile.TemporaryDirectory() as directory:
            openai = FakeOpenAI()
            paths = self.make_paths(Path(directory), ["fact_sales.csv", "analysis_helper.py"])

            def fail(_ids):
                raise RuntimeError("agent failed")

            with self.assertRaisesRegex(RuntimeError, "agent failed"):
                provision_update(openai, paths, {"fact_sales.csv": "old-sales"}, fail)

            self.assertEqual(openai.files.deleted, ["file-1"])

    def test_reusable_files_exclude_refreshed_assets(self):
        state = {"files": {"fact_sales.csv": "f1", "analysis_helper.py": "h1", "dataset_catalog.json": "c1"}}

        self.assertEqual(reusable_files(state, lambda _id: None), {"fact_sales.csv": "f1"})

    def test_reusable_files_resolves_legacy_state_by_lookup(self):
        state = {"file_ids": ["f1", "h1"]}
        names = {"f1": "fact_sales.csv", "h1": "analysis_helper.py"}

        self.assertEqual(reusable_files(state, names.__getitem__), {"fact_sales.csv": "f1"})

    def test_updated_state_retains_previous_version_and_replaced_files(self):
        previous = {
            "agent_name": "agent",
            "agent_version": "8",
            "file_ids": ["f1", "h1"],
            "retained": [{"agent_version": "7", "file_ids": ["h0"]}],
        }

        state = updated_state(
            previous,
            agent_version="9",
            files={"fact_sales.csv": "f1", "analysis_helper.py": "h2"},
            model_deployment="gpt-5-mini",
            reasoning_effort="high",
        )

        self.assertEqual(state["agent_version"], "9")
        self.assertEqual(state["reasoning_effort"], "high")
        self.assertEqual(state["file_ids"], ["f1", "h2"])
        self.assertEqual(
            state["retained"],
            [{"agent_version": "7", "file_ids": ["h0"]}, {"agent_version": "8", "file_ids": ["h1"]}],
        )

    def test_cleanup_also_deletes_retained_versions_and_files(self):
        project = FakeProject()
        openai = FakeOpenAI()
        state = {
            "agent_name": "agent",
            "agent_version": "9",
            "file_ids": ["f1", "h2"],
            "retained": [{"agent_version": "8", "file_ids": ["h1"]}],
        }

        cleanup_recorded_resources(project, openai, state)

        self.assertEqual(project.agents.deleted, [("agent", "9"), ("agent", "8")])
        self.assertEqual(openai.files.deleted, ["f1", "h2", "h1"])


if __name__ == "__main__":
    unittest.main()
