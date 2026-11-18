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
import tomllib
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
        roles = {}
        for path in (self.target / "agents").glob("*.toml"):
            profile = tomllib.loads(path.read_text())
            roles[profile["name"]] = path.stem
            self.assertNotIn("model", profile)
            self.assertNotIn("model_reasoning_effort", profile)
        self.assertEqual(roles, {name.replace("-", "_"): name for name in
                                 ("ladder-scout", "ladder-worker", "ladder-deep-worker", "ladder-verifier")})
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

    def test_upgrade_unpins_stock_roles_and_preserves_locally_edited_pins(self):
        former_defaults = {
            "ladder-scout": ("gpt-6-luna", "high"),
            "ladder-worker": ("gpt-6.1-sol", "medium"),
            "ladder-deep-worker": ("gpt-6-astra", "high"),
            "ladder-verifier": ("gpt-6.1-sol", "high"),
        }
        profiles = self.source / "assets/subagents"
        for name, (model, effort) in former_defaults.items():
            path = profiles / f"{name}.toml"
            pins = f'model = "{model}"\nmodel_reasoning_effort = "{effort}"\n'
            path.write_text(path.read_text().replace("developer_instructions =", pins + "developer_instructions ="))
        self.assertEqual(self.run_install(), 0)
        # Recreate the schema-1 ownership record written by cc60ae3. The old
        # installer recorded its own normalized digest and the exact role bytes.
        manifest = self.manifest()
        del manifest["legacy_profiles"]
        script_key = self.layout.key(self.layout.skill / "scripts/install.py")
        manifest["files"][script_key] = "ae6a27b3a3e645c4d80f4563d9370b539c3379a690888457531a2af442679f91"
        manifest_path = self.target / f"{installer.NAME}.manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        (self.layout.skill / "scripts/install.py").unlink()
        custom = self.worker().read_bytes().replace(b"gpt-6.1-sol", b"user-model").replace(b"medium", b"high")
        self.worker().write_bytes(custom)
        for path in profiles.glob("*.toml"):
            path.write_bytes((PACKAGE / "assets/subagents" / path.name).read_bytes())

        self.assertEqual(self.run_install(), 1)
        for path in (self.target / "agents").glob("*.toml"):
            if path == self.worker():
                self.assertEqual(path.read_bytes(), custom)
            else:
                self.assertEqual(path.read_text(), (profiles / path.name).read_text())
        self.assertEqual(self.run_install(), 1)
        self.assertEqual(self.run_install(uninstall=True), 1)
        self.assertEqual(self.worker().read_bytes(), custom)

    def test_pins_from_custom_bundles_survive_interrupted_upgrade_and_uninstall(self):
        profiles = self.source / "assets/subagents"
        for name, pins in {
            "ladder-scout": 'model = "custom-model"',
            "ladder-worker": 'model_reasoning_effort = "high"',
            "ladder-verifier": 'model = "custom-model"\nmodel_reasoning_effort = "low"',
        }.items():
            path = profiles / f"{name}.toml"
            path.write_text(pins + "\n" + path.read_text())
        self.assertEqual(self.run_install(), 0)
        saved = {}
        for path in profiles.glob("*.toml"):
            if path.stem == "ladder-deep-worker":
                continue
            for installed in (self.layout.skill / "assets/subagents", self.target / "agents"):
                saved[installed / path.name] = (installed / path.name).read_bytes()
            path.write_bytes((PACKAGE / "assets/subagents" / path.name).read_bytes())

        self.assertEqual(self.run_install(dry_run=True), 1)
        self.interrupt_after(lambda change: change.action == "record ownership")
        self.assertEqual(self.run_install(uninstall=True), 0)
        for installed, original in saved.items():
            self.assertEqual(installed.read_bytes(), original)

    def test_explicit_former_defaults_survive_a_stock_upgrade(self):
        path = self.source / "assets/subagents/ladder-worker.toml"
        role = path.read_text()
        pins = 'model = "gpt-6.1-sol"\nmodel_reasoning_effort = "medium"\n'
        path.write_text(role.replace("developer_instructions =", pins + "developer_instructions ="))
        self.assertEqual(self.run_install(), 0)
        original = self.worker().read_bytes()
        self.assertIn(installer.digest(original), installer.LEGACY_ROLES)
        # An install made by the first unpinned release had no migration field.
        manifest = self.manifest()
        del manifest["legacy_profiles"]
        (self.target / f"{installer.NAME}.manifest.json").write_text(json.dumps(manifest))
        path.write_text(role)
        self.assertEqual(self.run_install(), 1)
        self.assertEqual(self.run_install(uninstall=True), 0)
        self.assertEqual(self.worker().read_bytes(), original)
        self.assertEqual((self.layout.skill / "assets/subagents" / path.name).read_bytes(), original)

    def test_unowned_installer_cannot_identify_an_explicit_pin_as_stock(self):
        path = self.source / "assets/subagents/ladder-worker.toml"
        role = path.read_text()
        pins = 'model = "gpt-6.1-sol"\nmodel_reasoning_effort = "medium"\n'
        path.write_text(role.replace("developer_instructions =", pins + "developer_instructions ="))
        unowned = self.layout.skill / "scripts/install.py"
        unowned.parent.mkdir(parents=True)
        unowned.write_bytes(b"# Unowned installer from an older package.\n")
        self.assertEqual(self.run_install(), 1)
        original = self.worker().read_bytes()
        manifest = self.manifest()
        self.assertNotIn(self.layout.key(unowned), manifest["files"])
        del manifest["legacy_profiles"]
        (self.target / f"{installer.NAME}.manifest.json").write_text(json.dumps(manifest))
        path.write_text(role)
        with mock.patch.object(installer, "LEGACY_INSTALLERS", {installer.digest(unowned.read_bytes())}):
            self.assertEqual(self.run_install(), 1)
        self.assertEqual(self.worker().read_bytes(), original)
        self.assertEqual((self.layout.skill / "assets/subagents" / path.name).read_bytes(), original)

    def test_effort_only_update_preserves_existing_model_pin(self):
        path = self.source / "assets/subagents/ladder-worker.toml"
        role = path.read_text()
        path.write_text('model = "my-model"\n' + role)
        self.assertEqual(self.run_install(), 0)
        original = self.worker().read_bytes()
        path.write_text('model_reasoning_effort = "high"\n' + role)
        self.assertEqual(self.run_install(), 1)
        self.assertEqual(self.worker().read_bytes(), original)
        self.assertEqual(self.run_install(force=True), 0)
        self.assertEqual(self.worker().read_text(), path.read_text())
        backup, = self.worker().parent.glob("ladder-worker.toml.*.bak")
        self.assertEqual(backup.read_bytes(), original)

    def test_force_interruption_before_backup_keeps_original_pins_on_uninstall(self):
        path = self.source / "assets/subagents/ladder-worker.toml"
        role = path.read_bytes()
        path.write_bytes(b'model = "my-model"\n' + role)
        self.assertEqual(self.run_install(), 0)
        original = self.worker().read_bytes()
        path.write_bytes(role)
        with mock.patch.object(installer, "execute", side_effect=OSError("before backup")):
            with self.assertRaisesRegex(OSError, "before backup"):
                self.run_install(force=True)
        self.assertEqual(self.run_install(uninstall=True), 1)
        self.assertEqual(self.worker().read_bytes(), original)
        self.assertEqual((self.layout.skill / "assets/subagents" / path.name).read_bytes(), original)

    def test_invalid_optional_pins_rejected_before_writes(self):
        path = self.source / "assets/subagents/ladder-worker.toml"
        role = path.read_text()
        for pin in ('model = " "', 'model = []', 'model_reasoning_effort = []',
                    'model_reasoning_effort = "unknown"'):
            with self.subTest(pin=pin):
                path.write_text(pin + "\n" + role)
                with self.assertRaisesRegex(ValueError, "Invalid"):
                    self.run_install()
                self.assertFalse(self.target.exists())

    def test_source_update_replaces_unmodified_owned_file(self):
        self.run_install()
        profile = self.source / "assets/subagents/ladder-worker.toml"
        profile.write_text('model_reasoning_effort = "high"\n' + profile.read_text())
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
        profile.write_text('model_reasoning_effort = "high"\n' + profile.read_text())
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

    def test_interrupted_uninstall_from_installed_source_can_finish(self):
        self.assertEqual(self.run_install(), 0)
        self.source = self.layout.skill
        self.interrupt_after(lambda change: change.path == self.source / "SKILL.md", uninstall=True)
        self.assertFalse((self.source / "SKILL.md").exists())
        script = self.source / "scripts/install.py"
        result = subprocess.run([sys.executable, str(script), "--codex-dir", str(self.target),
                                 "--uninstall"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.worker().exists())
        self.assertFalse(script.exists())

    def test_uninstall_preserves_malformed_bundled_customization(self):
        self.assertEqual(self.run_install(), 0)
        self.source = self.layout.skill
        profile = self.source / "assets/subagents/ladder-scout.toml"
        profile.write_bytes(b"invalid TOML customization [")
        self.assertEqual(self.run_install(uninstall=True), 1)
        self.assertEqual(profile.read_bytes(), b"invalid TOML customization [")
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
