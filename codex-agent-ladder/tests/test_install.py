"""Exercise filesystem ownership, automatic routing, and reversible maintenance."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ladder_install", PACKAGE / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ladder-test-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        shutil.copytree(PACKAGE, self.source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.target = self.root / "profile"
        self.layout = installer.Layout.make(str(self.target), None)

    def tearDown(self):
        self.temp.cleanup()

    def run_install(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return installer.maintain(self.source, self.layout, **kwargs)

    def files(self):
        if not self.target.exists():
            return {}
        return {p.relative_to(self.target).as_posix(): p.read_bytes()
                for p in self.target.rglob("*") if p.is_file()}

    def manifest(self):
        return json.loads((self.layout.codex / f"{installer.NAME}.manifest.json").read_text())

    def worker(self):
        return self.layout.codex / "agents/ladder-worker.toml"

    def test_install_verify_and_idempotency(self):
        self.assertEqual(self.run_install(), 0)
        self.assertEqual(len(list((self.target / "agents").glob("*.toml"))), 4)
        self.assertIn(installer.BEGIN, (self.target / "AGENTS.md").read_text())
        before = self.files()
        times = {p: p.stat().st_mtime_ns for p in self.target.rglob("*") if p.is_file()}
        self.assertEqual(self.run_install(), 0)
        self.assertEqual(before, self.files())
        self.assertEqual(times, {p: p.stat().st_mtime_ns for p in self.target.rglob("*") if p.is_file()})
        self.assertEqual(self.run_install(verify=True), 0)

    def test_dry_run_creates_nothing(self):
        self.assertEqual(self.run_install(dry_run=True), 0)
        self.assertFalse(self.target.exists())

    def test_existing_guidance_and_config_are_preserved(self):
        self.target.mkdir()
        original = b"# My rules\r\nUse the project test runner.\r\n"
        (self.target / "AGENTS.md").write_bytes(original)
        config = b'model = "my-custom-model"\n'
        (self.target / "config.toml").write_bytes(config)
        self.assertEqual(self.run_install(), 0)
        guidance = (self.target / "AGENTS.md").read_bytes()
        self.assertTrue(guidance.startswith(original))
        self.assertNotIn(b"\n", guidance.replace(b"\r\n", b""))
        self.assertEqual((self.target / "config.toml").read_bytes(), config)

    def test_nonempty_override_receives_automatic_routing(self):
        self.target.mkdir()
        (self.target / "AGENTS.md").write_text("base instructions\n")
        override = self.target / "AGENTS.override.md"
        override.write_text("override instructions\n")
        self.assertEqual(self.run_install(), 0)
        self.assertIn(installer.BEGIN, override.read_text())
        self.assertEqual((self.target / "AGENTS.md").read_text(), "base instructions\n")

    def test_empty_override_does_not_hide_base_instructions(self):
        self.target.mkdir()
        (self.target / "AGENTS.override.md").write_bytes(b"")
        (self.target / "AGENTS.md").write_text("base instructions\n")
        self.assertEqual(self.run_install(), 0)
        self.assertEqual((self.target / "AGENTS.override.md").read_bytes(), b"")
        self.assertIn(installer.BEGIN, (self.target / "AGENTS.md").read_text())

    def test_unowned_conflict_is_skipped_and_not_claimed(self):
        self.worker().parent.mkdir(parents=True)
        self.worker().write_text("my agent\n")
        self.assertEqual(self.run_install(), 1)
        self.assertEqual(self.worker().read_text(), "my agent\n")
        self.assertNotIn("agents/ladder-worker.toml", self.manifest()["files"])
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertEqual(self.worker().read_text(), "my agent\n")

    def test_identical_preexisting_profile_is_not_owned(self):
        self.worker().parent.mkdir(parents=True)
        data = installer.normalized((self.source / "assets/subagents/ladder-worker.toml").read_text()).encode()
        self.worker().write_bytes(data)
        self.assertEqual(self.run_install(), 0)
        self.assertNotIn("agents/ladder-worker.toml", self.manifest()["files"])
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertEqual(self.worker().read_bytes(), data)

    def test_owned_customization_survives_update_and_uninstall(self):
        self.run_install()
        custom = self.worker().read_bytes() + b"\n# customized\n"
        self.worker().write_bytes(custom)
        self.assertEqual(self.run_install(), 1)
        self.assertEqual(self.worker().read_bytes(), custom)
        self.assertEqual(self.run_install(uninstall=True), 1)
        self.assertEqual(self.worker().read_bytes(), custom)
        self.assertIn("agents/ladder-worker.toml", self.manifest()["files"])
        self.assertNotIn(installer.BEGIN, (self.target / "AGENTS.md").read_text())

    def test_source_update_replaces_unmodified_owned_file(self):
        self.run_install()
        profile = self.source / "assets/subagents/ladder-worker.toml"
        profile.write_text(profile.read_text().replace('"medium"', '"high"'))
        self.assertEqual(self.run_install(), 0)
        self.assertIn('model_reasoning_effort = "high"', self.worker().read_text())
        self.assertEqual(self.run_install(verify=True), 0)

    def test_force_preserves_exact_conflicting_file_in_backup(self):
        self.worker().parent.mkdir(parents=True)
        custom = b"my unrelated agent\r\n"
        self.worker().write_bytes(custom)
        self.assertEqual(self.run_install(force=True), 0)
        backups = list(self.worker().parent.glob("ladder-worker.toml.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), custom)
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertEqual(backups[0].read_bytes(), custom)

    def test_uninstall_removes_owned_resources_and_only_routing_span(self):
        self.target.mkdir()
        original = b"# Existing instructions\nAlways use pnpm.\n"
        guidance = self.target / "AGENTS.md"
        guidance.write_bytes(original)
        self.run_install()
        installed = guidance.read_text()
        start, end = installer.bounds(installed)
        expected = (installed[:start] + installed[end:]).encode()
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertEqual(guidance.read_bytes(), expected)
        self.assertTrue(guidance.read_bytes().startswith(original))
        self.assertFalse(self.worker().exists())
        self.assertFalse((self.target / f"{installer.NAME}.manifest.json").exists())

    def test_custom_routing_survives_update_and_uninstall(self):
        self.run_install()
        guidance = self.target / "AGENTS.md"
        custom = guidance.read_text().replace("Keep quick or dependent steps", "Keep all dependent steps")
        guidance.write_text(custom)
        self.assertEqual(self.run_install(), 1)
        self.assertEqual(guidance.read_text(), custom)
        self.assertEqual(self.run_install(uninstall=True), 1)
        self.assertEqual(guidance.read_text(), custom)
        self.assertIsNotNone(self.manifest()["rules"])

    def test_routing_source_update_keeps_outside_text_exact(self):
        self.target.mkdir()
        guidance = self.target / "AGENTS.md"
        guidance.write_bytes(b"\xef\xbb\xbf# Rules\r\nDo useful work.\r\n")
        self.run_install()
        prior = guidance.read_bytes().decode()
        start, end = installer.bounds(prior)
        routing = self.source / "assets/routing.md"
        routing.write_text(routing.read_text().replace("Keep quick", "Keep small"))
        self.assertEqual(self.run_install(), 0)
        after = guidance.read_bytes().decode()
        new_start, new_end = installer.bounds(after)
        self.assertEqual(prior[:start], after[:new_start])
        self.assertEqual(prior[end:], after[new_end:])

    def test_malformed_guidance_rejected_before_writes(self):
        cases = [installer.BEGIN, installer.END + "\n" + installer.BEGIN,
                 "```\nunclosed", "```\n" + installer.BEGIN + "\n" + installer.END + "\n```"]
        self.target.mkdir()
        for text in cases:
            (self.target / "AGENTS.md").write_text(text)
            before = self.files()
            with self.assertRaises(ValueError):
                self.run_install()
            self.assertEqual(before, self.files())

    def test_invalid_toml_rejected_before_writes(self):
        (self.source / "assets/subagents/ladder-worker.toml").write_text('model = [')
        with self.assertRaises(ValueError):
            self.run_install()
        self.assertFalse(self.target.exists())

    def test_profile_permission_override_rejected_before_writes(self):
        profile = self.source / "assets/subagents/ladder-scout.toml"
        profile.write_text('sandbox_mode = "read-only"\n' + profile.read_text())
        with self.assertRaisesRegex(ValueError, "parent session"):
            self.run_install()
        self.assertFalse(self.target.exists())

    def interrupt_after(self, predicate, **kwargs):
        execute = installer.execute

        def interrupted(changes, layout, dry_run):
            for change in changes:
                execute([change], layout, dry_run)
                if predicate(change):
                    raise OSError("injected interruption")
            self.fail("Interruption point was not reached")

        with mock.patch.object(installer, "execute", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                self.run_install(**kwargs)

    def test_interrupted_install_retry_retains_ownership(self):
        self.interrupt_after(lambda change: change.path == self.layout.skill / "SKILL.md")
        before = self.files()
        self.assertEqual(self.run_install(verify=True), 1)
        self.assertEqual(self.run_install(dry_run=True), 1)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.run_install(), 0)
        self.assertEqual(self.run_install(verify=True), 0)
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertFalse((self.layout.skill / "SKILL.md").exists())
        self.assertFalse((self.target / f"{installer.NAME}.transaction.json").exists())

    def test_interrupted_install_preserves_subsequent_customization(self):
        self.interrupt_after(lambda change: change.path == self.layout.skill / "SKILL.md")
        installed = self.layout.skill / "SKILL.md"
        custom = installed.read_bytes() + b"\nUser customization\n"
        installed.write_bytes(custom)
        self.assertEqual(self.run_install(uninstall=True), 1)
        self.assertEqual(installed.read_bytes(), custom)

    def test_interrupted_update_recovers_new_hash_and_routing(self):
        self.assertEqual(self.run_install(), 0)
        profile = self.source / "assets/subagents/ladder-worker.toml"
        profile.write_text(profile.read_text().replace('"medium"', '"high"'))
        routing = self.source / "assets/routing.md"
        routing.write_text(routing.read_text().replace("Keep quick", "Keep small"))
        self.interrupt_after(lambda change: change.path == self.target / "AGENTS.md")
        self.assertEqual(self.run_install(), 0)
        self.assertEqual(self.run_install(verify=True), 0)
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertFalse(self.worker().exists())
        self.assertNotIn(installer.BEGIN, (self.target / "AGENTS.md").read_text())

    def test_interrupted_uninstall_can_finish(self):
        self.assertEqual(self.run_install(), 0)
        self.interrupt_after(lambda change: change.action == "remove", uninstall=True)
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertFalse((self.layout.skill / "SKILL.md").exists())
        self.assertFalse(self.worker().exists())
        self.assertNotIn(installer.BEGIN, (self.target / "AGENTS.md").read_text())

    def test_invalid_transaction_rejected_without_mutation(self):
        self.interrupt_after(lambda change: change.path == self.layout.skill / "SKILL.md")
        journal = self.target / f"{installer.NAME}.transaction.json"
        record = json.loads(journal.read_text())
        record["after"]["files"]["../outside.txt"] = "0" * 64
        journal.write_text(json.dumps(record))
        before = self.files()
        with self.assertRaises(ValueError):
            self.run_install()
        self.assertEqual(before, self.files())

    def test_manifest_traversal_is_rejected(self):
        self.run_install()
        manifest = self.target / f"{installer.NAME}.manifest.json"
        data = self.manifest()
        data["files"]["../outside.txt"] = "0" * 64
        manifest.write_text(json.dumps(data))
        before = self.files()
        with self.assertRaises(ValueError):
            self.run_install(uninstall=True)
        self.assertEqual(before, self.files())

    def test_symlinked_destination_is_never_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.target.mkdir()
        try:
            (self.target / "agents").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires Windows Developer Mode or privileges")
        with self.assertRaises(ValueError):
            self.run_install(force=True)
        self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_junction_rejected_even_without_pathlib_junction_api(self):
        self.target.mkdir()
        redirect = self.target / "redirect"
        redirect.mkdir()
        junction = self.target / "agents"
        result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(redirect)],
                                capture_output=True, text=True)
        if result.returncode:
            self.skipTest("Creating a test junction is unavailable")
        # is_junction arrived in Python 3.12. The installer uses lstat attributes.
        original_api = getattr(Path, "is_junction", None)
        try:
            if original_api is not None:
                delattr(Path, "is_junction")
            with self.assertRaises(ValueError):
                self.run_install(force=True)
        finally:
            if original_api is not None:
                Path.is_junction = original_api
        self.assertEqual(list(redirect.iterdir()), [])

    def test_verify_does_not_modify_files(self):
        self.run_install()
        self.worker().unlink()
        before = self.files()
        self.assertEqual(self.run_install(verify=True), 1)
        self.assertEqual(before, self.files())

    def test_project_layout_uses_project_guidance_and_skill_directory(self):
        project = self.root / "repository"
        project.mkdir()
        self.layout = installer.Layout.make(None, str(project))
        self.target = project
        self.assertEqual(self.run_install(), 0)
        self.assertTrue((project / ".agents/skills/codex-agent-ladder/SKILL.md").exists())
        self.assertTrue((project / ".codex/agents/ladder-scout.toml").exists())
        self.assertIn(installer.BEGIN, (project / "AGENTS.md").read_text())
        self.assertEqual(self.run_install(verify=True), 0)

    def test_active_guidance_change_is_reported_without_mutation(self):
        self.run_install()
        (self.target / "AGENTS.override.md").write_text("new override\n")
        before = self.files()
        self.assertEqual(self.run_install(verify=True), 1)
        with self.assertRaises(ValueError):
            self.run_install()
        self.assertEqual(before, self.files())
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertEqual((self.target / "AGENTS.override.md").read_text(), "new override\n")

    def test_preexisting_identical_routing_is_preserved_on_uninstall(self):
        self.target.mkdir()
        existing = (self.source / "assets/routing.md").read_bytes()
        guidance = self.target / "AGENTS.md"
        guidance.write_bytes(existing)
        self.assertEqual(self.run_install(), 0)
        self.assertIsNone(self.manifest()["rules"])
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertEqual(guidance.read_bytes(), existing)

    def test_crlf_source_installs_normalized_profiles(self):
        source_file = self.source / "assets/subagents/ladder-scout.toml"
        source_file.write_bytes(source_file.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.run_install(), 0)
        installed = self.target / "agents/ladder-scout.toml"
        self.assertNotIn(b"\r", installed.read_bytes())
        self.assertEqual(self.run_install(verify=True), 0)


if __name__ == "__main__":
    unittest.main()
