import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import claude_process


class ProcessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows taskkill policy")
    def test_taskkill_failure_does_not_claim_descendants_are_dead(self):
        child = Mock(pid=12345)
        child.poll.side_effect = [None, 0]
        with patch.object(claude_process.subprocess, "run", return_value=Mock(returncode=128)):
            with self.assertRaises(claude_process.ProcessCleanupError):
                claude_process.stop_child(child)
        child.kill.assert_not_called()
        child.wait.assert_called_once()

    def test_bounded_capture_with_inheriting_grandchild(self):
        code = ("import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "print('started',flush=True); time.sleep(30)")
        began = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            claude_process.run_capture([sys.executable, "-c", code], timeout=.5)
        self.assertLess(time.monotonic() - began, 10)

    def test_capture_preserves_bytes_and_return_code(self):
        result = claude_process.run_capture([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'raw\\x00bytes'); sys.exit(3)"], timeout=10)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"raw\x00bytes")

    def test_repeated_signals_are_ignored_during_cleanup_then_restored(self):
        before = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        with claude_process.cleanup_signals():
            for number in before:
                self.assertEqual(signal.getsignal(number), signal.SIG_IGN)
                signal.raise_signal(number)
        for number, previous in before.items():
            self.assertEqual(signal.getsignal(number), previous)

    def test_resolver_ignores_implicit_cwd_and_relative_path_entries(self):
        original = Path.cwd()
        actual = claude_process.resolve_on_path("git")
        with tempfile.TemporaryDirectory(prefix="claude-path-test-") as temporary:
            root = Path(temporary).resolve()
            fake = root / ("git.exe" if os.name == "nt" else "git")
            fake.write_bytes(b"not the Git executable")
            fake.chmod(0o755)
            try:
                os.chdir(root)
                with patch.dict(os.environ, {"PATH": "." + os.pathsep + str(Path(actual).parent)}):
                    self.assertEqual(claude_process.resolve_on_path("git"), actual)
            finally:
                os.chdir(original)


if __name__ == "__main__":
    unittest.main()
