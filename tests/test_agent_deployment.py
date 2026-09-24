import json
import tempfile
import unittest
from pathlib import Path

from scripts.create_agent import (
    cleanup_recorded_resources,
    load_state,
    prompt_agent_options,
    provision_resources,
    required_config,
    save_state,
)


class FakeFiles:
    def __init__(self, fail_on: int | None = None):
        self.fail_on = fail_on
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


class FakeOpenAI:
    def __init__(self, fail_on: int | None = None):
        self.files = FakeFiles(fail_on)


class FakeAgents:
    def __init__(self):
        self.deleted: list[tuple[str, str]] = []

    def delete_version(self, *, agent_name, agent_version):
        self.deleted.append((agent_name, agent_version))


class FakeProject:
    def __init__(self):
        self.agents = FakeAgents()


class ConfigTests(unittest.TestCase):
    def test_requires_existing_environment_names(self):
        with self.assertRaisesRegex(ValueError, "FOUNDRY_PROJECT_ENDPOINT"):
            required_config({})

    def test_accepts_the_approved_model(self):
        config = required_config(
            {
                "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/project",
                "FOUNDRY_MODEL_DEPLOYMENT": "gpt-4.1-mini",
                "FOUNDRY_AGENT_NAME": "manufacturing-agent",
            }
        )
        self.assertEqual(config["agent_name"], "manufacturing-agent")

    def test_rejects_a_different_model(self):
        with self.assertRaisesRegex(ValueError, "gpt-4.1-mini"):
            required_config(
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/project",
                    "FOUNDRY_MODEL_DEPLOYMENT": "other-model",
                    "FOUNDRY_AGENT_NAME": "manufacturing-agent",
                }
            )

    def test_prompt_agent_uses_deterministic_temperature(self):
        options = prompt_agent_options("gpt-4.1-mini", "instructions", ["tool"])

        self.assertEqual(options["temperature"], 0)
        self.assertEqual(options["model"], "gpt-4.1-mini")


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


if __name__ == "__main__":
    unittest.main()
