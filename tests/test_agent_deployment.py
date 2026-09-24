import json
import tempfile
import unittest
from pathlib import Path

from scripts.create_agent import (
    cleanup_recorded_resources,
    finalize_deployment,
    load_state,
    prompt_agent_options,
    provision_resources,
    required_config,
    save_state,
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

    def test_prompt_agent_uses_medium_reasoning_without_sampling_temperature(self):
        options = prompt_agent_options("gpt-5-mini", "instructions", ["tool"])

        self.assertEqual(options["reasoning"], {"effort": "medium"})
        self.assertNotIn("temperature", options)
        self.assertEqual(options["model"], "gpt-5-mini")


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


if __name__ == "__main__":
    unittest.main()
