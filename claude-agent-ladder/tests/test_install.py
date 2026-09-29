import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install.py"
BEGIN = "<!-- claude-agent-ladder:begin -->"
END = "<!-- claude-agent-ladder:end -->"
NAMES = ["deep-worker", "explorer", "fast-worker", "planner", "scout", "std-worker", "verifier"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-claude-agent-ladder-")
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.agents = self.dir / "agents"
        self.claude_md = self.dir / "CLAUDE.md"
        self.manifest = self.dir / "claude-agent-ladder.manifest.json"
        self.rules = (ROOT / "rules.md").read_bytes().replace(b"\r\n", b"\n").decode("utf-8")

    def run_install(self, *args, env=None, with_dir=True):
        cmd = [sys.executable, str(SCRIPT)]
        if with_dir:
            cmd += ["--claude-dir", str(self.dir)]
        e = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        e.update(env or {})
        return subprocess.run(cmd + list(args), capture_output=True, text=True, env=e)

    def src(self, name):
        return (ROOT / "subagents" / f"{name}.md").read_bytes().replace(b"\r\n", b"\n")

    def test_fresh_install(self):
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for n in NAMES:
            self.assertEqual((self.agents / f"{n}.md").read_bytes(), self.src(n))
            self.assertIn(f"agents/{n}.md: created", r.stdout)
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "1.0.0")
        self.assertEqual(data["agents"], {f"{n}.md": sha(self.src(n)) for n in NAMES})
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertIn(BEGIN + "\n" + self.rules, text)
        self.assertTrue(text.endswith(END + "\n"))
        self.assertIn("CLAUDE.md rules block: created", r.stdout)
        self.assertTrue(r.stdout.strip().endswith("claude-agent-ladder 1.0.0: done"))

    def test_second_run_unchanged(self):
        self.run_install()
        before = self.claude_md.read_bytes()
        r = self.run_install()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.count(": unchanged"), 9)
        self.assertIn("claude-agent-ladder.manifest.json: unchanged", r.stdout)
        self.assertNotIn("created", r.stdout)
        self.assertEqual(self.claude_md.read_bytes(), before)

    def test_upgrade_path(self):
        self.run_install()
        old = b"old version of scout\n"
        (self.agents / "scout.md").write_bytes(old)
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["agents"]["scout.md"] = sha(old)
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("agents/scout.md: updated", r.stdout)
        self.assertEqual((self.agents / "scout.md").read_bytes(), self.src("scout"))
        self.assertFalse((self.agents / "scout.md.bak").exists())

    def test_foreign_file_skipped(self):
        self.agents.mkdir()
        (self.agents / "scout.md").write_text("mine", encoding="utf-8")
        r = self.run_install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("agents/scout.md: skipped: modified locally", r.stdout)
        self.assertIn("done with conflicts", r.stdout)
        self.assertEqual((self.agents / "scout.md").read_text(encoding="utf-8"), "mine")
        self.assertNotIn("scout.md", json.loads(self.manifest.read_text(encoding="utf-8"))["agents"])
        self.assertTrue((self.agents / "explorer.md").exists())

    def test_force_backs_up(self):
        self.agents.mkdir()
        (self.agents / "scout.md").write_text("mine", encoding="utf-8")
        r = self.run_install("--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("agents/scout.md: replaced, backup at agents/scout.md.bak", r.stdout)
        self.assertEqual((self.agents / "scout.md.bak").read_text(encoding="utf-8"), "mine")
        self.assertEqual((self.agents / "scout.md").read_bytes(), self.src("scout"))

    def test_force_existing_bak_uses_numbered(self):
        self.agents.mkdir()
        (self.agents / "scout.md").write_text("mine", encoding="utf-8")
        (self.agents / "scout.md.bak").write_text("older", encoding="utf-8")
        r = self.run_install("--force")
        self.assertEqual(r.returncode, 0)
        self.assertEqual((self.agents / "scout.md.bak").read_text(encoding="utf-8"), "older")
        self.assertEqual((self.agents / "scout.md.bak.1").read_text(encoding="utf-8"), "mine")

    def test_preserves_surrounding_crlf(self):
        pre, post = "# Mine\r\nline\r\n", "\r\n## After\r\nend\r\n"
        self.dir.mkdir(exist_ok=True)
        self.claude_md.write_bytes(pre.encode())
        self.run_install()
        text = self.claude_md.read_bytes().decode()
        self.assertTrue(text.startswith(pre + "\r\n" + BEGIN + "\r\n"))
        self.assertNotIn("\n", text.replace("\r\n", ""))
        self.claude_md.write_bytes((text + post).encode())
        r = self.run_install()
        self.assertEqual(r.returncode, 0)
        self.assertIn("rules block: unchanged", r.stdout)
        self.assertEqual(self.claude_md.read_bytes().decode(), text + post)

    def test_replaces_existing_block(self):
        pre, post = "top\n\n", "\nbottom\n"
        self.claude_md.write_bytes(f"{pre}{BEGIN}\nstale\n{END}\n{post}".encode())
        r = self.run_install()
        self.assertEqual(r.returncode, 0)
        self.assertIn("CLAUDE.md rules block: updated", r.stdout)
        self.assertEqual(self.claude_md.read_bytes().decode(), f"{pre}{BEGIN}\n{self.rules}{END}\n{post}")

    def test_malformed_markers(self):
        cases = [f"{BEGIN}\nx\n", f"x\n{END}\n", f"{END}\n{BEGIN}\n",
                 f"{BEGIN}\n{END}\n{BEGIN}\n{END}\n"]
        for content in cases:
            with self.subTest(content=content):
                self.claude_md.write_bytes(content.encode())
                r = self.run_install()
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("failed", r.stdout)
                self.assertEqual(self.claude_md.read_bytes().decode(), content)

    def test_workflow_size_preserves_keys(self):
        (self.dir).mkdir(exist_ok=True)
        (self.dir / "settings.json").write_text(json.dumps({"model": "opus", "a": {"b": 1}}), encoding="utf-8")
        r = self.run_install("--workflow-size", "unrestricted")
        self.assertEqual(r.returncode, 0)
        self.assertIn("settings.json workflowSizeGuideline: unrestricted", r.stdout)
        raw = (self.dir / "settings.json").read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("}\n"))
        self.assertEqual(json.loads(raw),
                         {"model": "opus", "a": {"b": 1}, "workflowSizeGuideline": "unrestricted"})

    def test_workflow_size_missing_settings_and_default_untouched(self):
        self.run_install()
        self.assertFalse((self.dir / "settings.json").exists())
        self.run_install("--workflow-size", "small")
        self.assertEqual(json.loads((self.dir / "settings.json").read_text(encoding="utf-8")),
                         {"workflowSizeGuideline": "small"})

    def test_invalid_settings_json(self):
        (self.dir / "settings.json").write_text("{not json", encoding="utf-8")
        r = self.run_install("--workflow-size", "large")
        self.assertEqual(r.returncode, 2)
        self.assertEqual((self.dir / "settings.json").read_text(encoding="utf-8"), "{not json")

    def test_dry_run_writes_nothing(self):
        r = self.run_install("--dry-run", "--workflow-size", "medium")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("would agents/scout.md: created", r.stdout)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_uninstall(self):
        self.claude_md.write_text("keep me\n", encoding="utf-8")
        self.run_install("--workflow-size", "large")
        (self.agents / "scout.md").write_text("edited", encoding="utf-8")
        (self.agents / "other.md").write_text("unrelated", encoding="utf-8")
        settings = (self.dir / "settings.json").read_bytes()
        r = self.run_install("--uninstall")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("workflowSizeGuideline: left as is", r.stdout)
        self.assertEqual(sorted(p.name for p in self.agents.iterdir()), ["other.md", "scout.md"])
        self.assertEqual((self.agents / "scout.md").read_text(encoding="utf-8"), "edited")
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), "keep me\n")
        self.assertFalse(self.manifest.exists())
        self.assertEqual((self.dir / "settings.json").read_bytes(), settings)

    def test_uninstall_force_removes_modified(self):
        self.run_install()
        (self.agents / "scout.md").write_text("edited", encoding="utf-8")
        r = self.run_install("--uninstall", "--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertFalse((self.agents / "scout.md").exists())

    def test_no_rules(self):
        self.claude_md.write_text("untouched", encoding="utf-8")
        r = self.run_install("--no-rules")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), "untouched")
        fresh = self.dir / "sub"
        subprocess.run([sys.executable, str(SCRIPT), "--claude-dir", str(fresh), "--no-rules"],
                       capture_output=True)
        self.assertFalse((fresh / "CLAUDE.md").exists())

    def test_env_config_dir(self):
        r = self.run_install(env={"CLAUDE_CONFIG_DIR": str(self.dir)}, with_dir=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.agents / "scout.md").exists())

    # ---- review fixes ----

    def make_skill(self, sources=None, rules=None):
        skill = self.dir / "skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "subagents").mkdir()
        shutil.copy(SCRIPT, skill / "scripts" / "install.py")
        for name, data in (sources or {"scout.md": b"---\nname: scout\n---\n"}).items():
            (skill / "subagents" / name).write_bytes(data)
        (skill / "rules.md").write_bytes(rules if rules is not None else b"rule one\n")
        return skill / "scripts" / "install.py"

    def run_script(self, script, claude, *args):
        return subprocess.run([sys.executable, str(script), "--claude-dir", str(claude), *args],
                              capture_output=True, text=True)

    def link(self, link: Path, target: Path):
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")

    def snapshot(self):
        return {str(p.relative_to(self.dir)): (p.read_bytes() if p.is_file() else None)
                for p in sorted(self.dir.rglob("*"))}

    def test_symlinked_claude_md_install_and_uninstall(self):
        real = self.dir / "elsewhere" / "real-claude.md"
        real.parent.mkdir()
        real.write_text("mine\n", encoding="utf-8")
        self.link(self.claude_md, real)
        self.assertEqual(self.run_install().returncode, 0)
        self.assertTrue(self.claude_md.is_symlink())
        self.assertIn(BEGIN, real.read_text(encoding="utf-8"))
        self.assertTrue(real.read_text(encoding="utf-8").startswith("mine\n\n"))
        self.assertEqual(self.run_install("--uninstall").returncode, 0)
        self.assertTrue(self.claude_md.is_symlink())
        self.assertEqual(real.read_text(encoding="utf-8"), "mine\n")

    def test_symlinked_settings(self):
        real = self.dir / "elsewhere" / "real-settings.json"
        real.parent.mkdir()
        real.write_text('{"x": 1}', encoding="utf-8")
        self.link(self.dir / "settings.json", real)
        self.assertEqual(self.run_install("--workflow-size", "small").returncode, 0)
        self.assertTrue((self.dir / "settings.json").is_symlink())
        self.assertEqual(json.loads(real.read_text(encoding="utf-8")), {"x": 1, "workflowSizeGuideline": "small"})

    def test_symlinked_agent_updated(self):
        self.run_install()
        old = b"old scout\n"
        real = self.dir / "elsewhere" / "scout-real.md"
        real.parent.mkdir()
        real.write_bytes(old)
        (self.agents / "scout.md").unlink()
        self.link(self.agents / "scout.md", real)
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["agents"]["scout.md"] = sha(old)
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        r = self.run_install()
        self.assertIn("agents/scout.md: updated", r.stdout)
        self.assertTrue((self.agents / "scout.md").is_symlink())
        self.assertEqual(real.read_bytes(), self.src("scout"))

    def test_fenced_markers_ignored(self):
        fenced = f"```\n{BEGIN}\nfoo\n{END}\n```\n"
        self.claude_md.write_bytes(fenced.encode())
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stdout)
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(fenced + "\n" + BEGIN + "\n"))
        self.assertEqual(text.count(BEGIN), 2)
        r = self.run_install()
        self.assertIn("rules block: unchanged", r.stdout)
        self.run_install("--uninstall")
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), fenced)

    def test_rules_containing_marker_rejected(self):
        script = self.make_skill(rules=f"a\n{END}\nb\n".encode())
        claude = self.dir / "c"
        r = self.run_script(script, claude)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertFalse(claude.exists())

    def test_latin1_claude_md_install(self):
        self.claude_md.write_bytes(b"caf\xe9\n")
        r = self.run_install()
        self.assertEqual(r.returncode, 2)
        self.assertIn("CLAUDE.md: cannot read as UTF-8", r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(self.agents.exists())
        self.assertFalse(self.manifest.exists())
        self.assertEqual(self.claude_md.read_bytes(), b"caf\xe9\n")

    def test_latin1_claude_md_uninstall(self):
        self.run_install("--no-rules")
        self.claude_md.write_bytes(b"caf\xe9\n")
        before = self.snapshot()
        r = self.run_install("--uninstall")
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot read as UTF-8", r.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_unsafe_manifest_key_ignored(self):
        self.claude_md.write_text("precious\n", encoding="utf-8")
        self.manifest.write_text(json.dumps(
            {"version": "0", "agents": {"../CLAUDE.md": sha(b"precious\n"), "x.txt": "0"}}))
        r = self.run_install("--uninstall", "--no-rules")
        self.assertIn("note: ignoring unsafe manifest entry '../CLAUDE.md'", r.stdout)
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), "precious\n")
        self.manifest.write_text(json.dumps(
            {"version": "0", "agents": {"../CLAUDE.md": sha(b"precious\n")}}))
        self.run_install("--no-rules")
        self.assertEqual(self.claude_md.read_text(encoding="utf-8"), "precious\n")
        self.assertNotIn("../CLAUDE.md", self.manifest.read_text(encoding="utf-8"))

    @unittest.skipIf(os.name == "nt", "posix permission bits")
    def test_file_mode_preserved(self):
        self.claude_md.write_text("x\n", encoding="utf-8")
        (self.dir / "settings.json").write_text("{}", encoding="utf-8")
        os.chmod(self.claude_md, 0o640)
        os.chmod(self.dir / "settings.json", 0o600)
        self.run_install("--workflow-size", "small")
        self.assertEqual(stat.S_IMODE(self.claude_md.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE((self.dir / "settings.json").stat().st_mode), 0o600)

    def test_marker_lines_with_trailing_whitespace(self):
        self.claude_md.write_bytes(f"{BEGIN}  \nstale\n{END}\t\nafter\n".encode())
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stdout)
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertEqual(text.count(BEGIN), 1)
        self.assertNotIn("stale", text)
        self.assertTrue(text.endswith("after\n"))

    def _stale_agent(self, content=b"old agent\n", registered=None):
        self.run_install()
        (self.agents / "old.md").write_bytes(content)
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["agents"]["old.md"] = sha(registered if registered is not None else content)
        self.manifest.write_text(json.dumps(data), encoding="utf-8")

    def test_unshipped_unmodified_removed(self):
        self._stale_agent()
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("agents/old.md: removed", r.stdout)
        self.assertFalse((self.agents / "old.md").exists())
        self.assertNotIn("old.md", self.manifest.read_text(encoding="utf-8"))

    def test_unshipped_modified_conflict_then_force(self):
        self._stale_agent(content=b"edited\n", registered=b"orig\n")
        r = self.run_install()
        self.assertEqual(r.returncode, 1)
        self.assertEqual((self.agents / "old.md").read_bytes(), b"edited\n")
        self.assertIn("old.md", self.manifest.read_text(encoding="utf-8"))
        (self.agents / "old.md.bak").write_bytes(b"prev")
        r = self.run_install("--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("agents/old.md: removed, backup at agents/old.md.bak.1", r.stdout)
        self.assertFalse((self.agents / "old.md").exists())
        self.assertEqual((self.agents / "old.md.bak.1").read_bytes(), b"edited\n")

    def test_crlf_sources_normalized(self):
        script = self.make_skill(sources={"scout.md": b"---\r\nname: scout\r\n---\r\nbody\r\n"},
                                 rules=b"r1\r\nr2\r\n")
        claude = self.dir / "c"
        r = self.run_script(script, claude)
        self.assertEqual(r.returncode, 0, r.stdout)
        data = (claude / "agents" / "scout.md").read_bytes()
        self.assertEqual(data, b"---\nname: scout\n---\nbody\n")
        self.assertEqual(json.loads((claude / MANIFEST_NAME).read_text(encoding="utf-8"))["agents"]["scout.md"], sha(data))
        self.assertNotIn(b"\r", (claude / "CLAUDE.md").read_bytes())

    def test_dry_run_force_over_conflict(self):
        self.agents.mkdir()
        (self.agents / "scout.md").write_text("mine", encoding="utf-8")
        before = self.snapshot()
        r = self.run_install("--dry-run", "--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("would agents/scout.md: replaced, backup at agents/scout.md.bak", r.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_dry_run_byte_identical(self):
        self.run_install("--workflow-size", "small")
        (self.agents / "scout.md").write_text("edited", encoding="utf-8")
        before = self.snapshot()
        r = self.run_install("--uninstall", "--dry-run", "--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("would agents/verifier.md: removed", r.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_unclosed_fence_install_fails_closed(self):
        content = b"# mine\n\n```\nunclosed example\n"
        self.claude_md.write_bytes(content)
        r = self.run_install()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("unclosed code fence", r.stdout)
        self.assertEqual(self.claude_md.read_bytes(), content)
        self.assertFalse(self.agents.exists())
        self.assertFalse(self.manifest.exists())

    def test_unclosed_fence_uninstall_fails_closed(self):
        self.run_install()
        content = b"# mine\n\n```\nunclosed example\n" + self.claude_md.read_bytes()
        self.claude_md.write_bytes(content)
        before = self.snapshot()
        r = self.run_install("--uninstall")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_indented_markers(self):
        self.claude_md.write_bytes(f"  {BEGIN}\nstale\n   {END}\nafter\n".encode())
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stdout)
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertEqual(text.count(BEGIN), 1)
        self.assertNotIn("stale", text)
        self.assertTrue(text.endswith("after\n"))

    def test_deeply_indented_markers_not_matched(self):
        for indent in ("    ", "\t"):
            with self.subTest(indent=repr(indent)):
                content = f"{indent}{BEGIN}\n{indent}{END}\n"
                self.claude_md.write_bytes(content.encode())
                r = self.run_install()
                self.assertEqual(r.returncode, 0, r.stdout)
                self.assertTrue(self.claude_md.read_text(encoding="utf-8").startswith(content + "\n" + BEGIN))

    def test_force_symlink_reports_target(self):
        real = self.dir / "elsewhere" / "scout-real.md"
        real.parent.mkdir()
        real.write_text("foreign", encoding="utf-8")
        self.agents.mkdir()
        self.link(self.agents / "scout.md", real)
        r = self.run_install("--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"symlink target {os.path.realpath(real)} overwritten", r.stdout)
        self.assertTrue((self.agents / "scout.md").is_symlink())
        self.assertEqual(real.read_bytes(), self.src("scout"))
        self.assertEqual((self.agents / "scout.md.bak").read_text(encoding="utf-8"), "foreign")
        (real).write_text("edited", encoding="utf-8")
        r = self.run_install("--uninstall", "--force")
        self.assertIn(f"symlink target {os.path.realpath(real)}", r.stdout)
        self.assertFalse((self.agents / "scout.md").is_symlink())
        self.assertEqual(real.read_text(encoding="utf-8"), "edited")


MANIFEST_NAME = "claude-agent-ladder.manifest.json"

class ShippedAgentTests(unittest.TestCase):
    def frontmatter(self, name):
        text = (ROOT / "subagents" / f"{name}.md").read_text(encoding="utf-8")
        return text.split("\n---\n", 1)

    def test_no_tier_can_use_monitor(self):
        for name in NAMES:
            head, _ = self.frontmatter(name)
            line = next((l for l in head.splitlines() if l.startswith("disallowedTools:")), "")
            tools = [t.strip() for t in line.partition(":")[2].split(",")]
            self.assertIn("Monitor", tools, name)

    def test_command_running_tiers_have_waiting_rule(self):
        for name in ("fast-worker", "std-worker", "deep-worker", "verifier"):
            _, body = self.frontmatter(name)
            self.assertIn("- Waiting:", body, name)
            self.assertIn("never start a second copy", body, name)


if __name__ == "__main__":
    unittest.main()
