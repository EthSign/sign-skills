"""Bounded process capture and tree cleanup shared by Git and Claude preflight."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading


class ProcessCleanupError(RuntimeError):
    pass


# SIGHUP is what a closing terminal or lost host session delivers. The child runs in its
# own session and never receives it, so the wrapper must treat it as a termination request.
TERMINATION_SIGNALS = tuple(getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, name))
# A caller such as a Git hook or `rebase --exec` exports these; inherited, they would
# redirect the wrapper's Git commands to another repository or to the caller's real index.
GIT_LOCATION_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                          "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX")


def git_environment():
    environment = {key: value for key, value in os.environ.items() if key not in GIT_LOCATION_VARIABLES}
    # Read-only commands such as diff and status must not refresh the source index.
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def resolve_on_path(name):
    """Resolve absolute PATH entries without Windows' implicit cwd lookup."""
    extensions = [""] if os.name != "nt" or Path(name).suffix.lower() in (".exe", ".com") else [".exe", ".com"]
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        directory = Path(entry.strip('"'))
        if not directory.is_absolute():
            continue
        for extension in extensions:
            candidate = directory / (name + extension)
            found = shutil.which(str(candidate))
            if found:
                return str(Path(found).resolve())
    raise FileNotFoundError(f"Executable not found on absolute PATH entries: {name}")


@contextmanager
def cleanup_signals():
    """Finish cleanup/publication even if termination is requested repeatedly."""
    saved = {}
    if threading.current_thread() is threading.main_thread():
        for number in TERMINATION_SIGNALS:
            saved[number] = signal.signal(number, signal.SIG_IGN)
    try:
        yield
    finally:
        for number, handler in saved.items():
            signal.signal(number, handler)


def stop_child(child):
    if child.poll() is not None:
        return
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        if not taskkill.is_absolute() or not taskkill.is_file():
            raise ProcessCleanupError("Trusted Windows taskkill executable is unavailable")
        killed = subprocess.run([str(taskkill), "/PID", str(child.pid), "/T", "/F"], capture_output=True, timeout=30)
        if killed.returncode:
            # A dead parent alone cannot confirm that /T terminated descendants.
            # Retain the isolated workspace when tree cleanup is uncertain.
            if child.poll() is None:
                child.kill()
            child.wait(timeout=30)
            raise ProcessCleanupError("Unable to confirm child process-tree termination")
    else:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    child.wait(timeout=30)


def run_capture(command, *, timeout, cwd=None, env=None):
    # Files, not PIPEs: an inherited grandchild handle must not make post-timeout
    # communicate() wait indefinitely for EOF after the direct process is killed.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        child = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                 env=env, start_new_session=os.name != "nt",
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            child.wait(timeout=timeout)
        finally:
            with cleanup_signals():
                stop_child(child)
        output.seek(0)
        errors.seek(0)
        return subprocess.CompletedProcess(command, child.returncode, output.read(), errors.read())
