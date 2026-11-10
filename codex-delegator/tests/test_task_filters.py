"""Task-only Git filter regressions; all repositories and markers are disposable."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("task_filter_runner", ROOT / "scripts" / "invoke-codex.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class TaskFilterTests(unittest.TestCase):
    def setUp(self):
        self.git_executable = runner.git_executable()
        self.temp = tempfile.TemporaryDirectory(prefix="test-task-filters-")
        self.root = Path(self.temp.name).resolve()
        self.source, self.task = self.root / "source", self.root / "task"
        self.source.mkdir()
        self.environment = patch.dict(os.environ, {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.temp.cleanup)
        self.git(self.source, "init", "-q")
        # A single native executable name avoids Git's shell wrapper. The
        # controlled fixture content is a benign Python program on stdin.
        self.native_filter = Path(sys.executable).name
        self.marker = self.source / ".git" / "benign-filter-marker.txt"

    def git(self, repo, *args, check=True):
        result = subprocess.run([self.git_executable, "-c", "core.hooksPath=" + os.devnull,
                                 "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                                capture_output=True, check=check)
        return result.stdout if check else result

    def filter_payload(self):
        return ("import pathlib; pathlib.Path(" + repr(str(self.marker)) +
                ").write_text('benign filter executed'); print('expanded filter bytes')\n").encode()

    def commit(self, files):
        for name, data in files.items():
            (self.source / name).write_bytes(data)
        runner.git(self.source, "add", "--all", task_filters=True)
        runner.git(self.source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                   "commit", "-qm", "baseline", task_filters=True)
        return self.git(self.source, "rev-parse", "HEAD").decode().strip()

    def materialize(self, head):
        runner.git(self.source, "worktree", "add", "--no-checkout", "--detach", str(self.task), head,
                   task_filters=True)
        runner.git(self.task, "reset", "--hard", head, task_filters=True)

    def collect(self, head):
        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        evidence = runner.collect_task_evidence(self.task, head, artifacts)
        return evidence, (artifacts / "task-diff.patch").read_bytes()

    def test_task_written_attributes_cannot_activate_host_clean_filter(self):
        head = self.commit({"payload.dat": b"baseline\n"})
        self.materialize(head)
        self.git(self.source, "config", "filter.fixture.clean", self.native_filter)
        (self.task / ".gitattributes").write_bytes(b"payload.dat filter=fixture -text\n")
        payload = self.filter_payload()
        (self.task / "payload.dat").write_bytes(payload)
        # Confirm the configured native filter really works in this fixture;
        # default review commands retain their existing filter behavior.
        runner.patch(self.task, head)
        self.assertTrue(self.marker.exists())
        self.marker.unlink()
        evidence, diff = self.collect(head)
        self.assertFalse(self.marker.exists())
        self.assertIn(b"benign filter executed", diff)
        self.assertEqual([".gitattributes", "payload.dat"], evidence["actual_changed_files"])
        self.assertEqual(payload, (self.task / "payload.dat").read_bytes())

    def test_initial_smudge_is_disabled_and_unchanged_evidence_is_empty(self):
        self.git(self.source, "config", "filter.fixture.clean", self.native_filter)
        self.git(self.source, "config", "filter.fixture.smudge", self.native_filter)
        self.git(self.source, "config", "filter.fixture.required", "true")
        payload = self.filter_payload()
        head = self.commit({".gitattributes": b"payload.dat filter=fixture -text\n", "payload.dat": payload})
        self.materialize(head)
        self.assertFalse(self.marker.exists())
        self.assertEqual(payload, (self.task / "payload.dat").read_bytes())
        evidence, diff = self.collect(head)
        self.assertFalse(self.marker.exists())
        self.assertEqual([], evidence["actual_changed_files"])
        self.assertEqual(b"", diff)

    def test_required_lfs_process_configuration_keeps_pointer_unexpanded(self):
        for operation in ("clean", "smudge", "process"):
            self.git(self.source, "config", "filter.lfs." + operation, "nonexistent-fixture-lfs-filter")
        self.git(self.source, "config", "filter.lfs.required", "true")
        pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 123\n"
        head = self.commit({".gitattributes": b"asset.bin filter=lfs -text\n", "asset.bin": pointer})
        self.materialize(head)
        self.assertEqual(pointer, (self.task / "asset.bin").read_bytes())
        evidence, diff = self.collect(head)
        self.assertEqual([], evidence["actual_changed_files"])
        self.assertEqual(b"", diff)

    def test_conditional_driver_is_resolved_in_new_worktree_context(self):
        payload = self.filter_payload()
        head = self.commit({".gitattributes": b"payload.dat filter=context -text\n", "payload.dat": payload})
        conditional = self.root / "conditional.config"
        conditional.write_text('[filter "context"]\nclean = ' + self.native_filter +
                               '\nsmudge = ' + self.native_filter + '\nrequired = true\n', encoding="utf-8")
        runner.git(self.source, "worktree", "add", "--no-checkout", "--detach", str(self.task), head,
                   task_filters=True)
        admin = self.git(self.task, "rev-parse", "--absolute-git-dir").decode().strip().replace("\\", "/")
        self.git(self.source, "config", "includeIf.gitdir/i:" + admin + ".path", str(conditional))
        self.assertEqual(1, self.git(self.source, "config", "--get", "filter.context.smudge", check=False).returncode)
        self.assertEqual(self.native_filter, self.git(self.task, "config", "--get", "filter.context.smudge").decode().strip())
        runner.git(self.task, "reset", "--hard", head, task_filters=True)
        self.assertFalse(self.marker.exists())
        self.assertEqual(payload, (self.task / "payload.dat").read_bytes())
        evidence, diff = self.collect(head)
        self.assertEqual([], evidence["actual_changed_files"])
        self.assertEqual(b"", diff)

    def test_dot_and_space_driver_names_are_overridden_exactly(self):
        for driver in ("nested.name", "with space"):
            with self.subTest(driver=driver):
                for operation in ("clean", "smudge", "process"):
                    key = "filter." + driver + "." + operation
                    self.git(self.source, "config", key, self.native_filter)
                self.git(self.source, "config", "filter." + driver + ".required", "true")
                for operation in ("clean", "smudge", "process"):
                    self.assertEqual(b"\n", runner.git(self.source, "config", "--get",
                                     "filter." + driver + "." + operation, task_filters=True))
                self.assertEqual(b"false\n", runner.git(self.source, "config", "--get",
                                 "filter." + driver + ".required", task_filters=True))

    def test_equals_driver_name_fails_closed_before_collection(self):
        head = self.commit({"payload.dat": b"baseline\n"})
        self.materialize(head)
        self.git(self.source, "config", "filter.equal=name.clean", self.native_filter)
        (self.task / ".gitattributes").write_bytes(b"payload.dat filter=equal=name -text\n")
        (self.task / "payload.dat").write_bytes(self.filter_payload())
        # Git accepts this subsection and attributes can select it, but the -c
        # override syntax cannot represent its '=' without ambiguity.
        runner.patch(self.task, head)
        self.assertTrue(self.marker.exists())
        self.marker.unlink()
        with self.assertRaisesRegex(ValueError, "Unsupported configured Git filter driver name"):
            self.collect(head)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
