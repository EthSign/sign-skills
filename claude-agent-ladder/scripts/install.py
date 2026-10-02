#!/usr/bin/env python3
"""Install claude-agent-ladder subagents and routing rules. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- claude-agent-ladder:begin -->"
END = "<!-- claude-agent-ladder:end -->"
MANIFEST = "claude-agent-ladder.manifest.json"
SIZES = ("small", "medium", "large", "unrestricted")
SKIP_MSG = ("skipped: modified locally or not installed by claude-agent-ladder; "
            "rerun with --force to replace (a backup is kept)")


class Run:
    def __init__(self, dry: bool):
        self.dry = dry
        self.conflicts = 0
        self.errors = 0

    def say(self, line: str) -> None:
        print(("would " if self.dry else "") + line)

    def error(self, line: str) -> None:
        self.errors += 1
        print("error: " + line)

    def conflict(self, line: str) -> None:
        self.conflicts += 1
        print(line)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    if path.is_symlink():
        path = Path(os.path.realpath(path))
    if path.exists():
        mode = stat.S_IMODE(path.stat().st_mode)
    else:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def backup_path(path: Path) -> Path:
    candidate = path.with_name(path.name + ".bak")
    n = 0
    while candidate.exists() or candidate.is_symlink():
        n += 1
        candidate = path.with_name(f"{path.name}.bak.{n}")
    return candidate


def valid_key(name: str) -> bool:
    return (name.endswith(".md") and Path(name).name == name
            and "/" not in name and "\\" not in name and name not in ("", ".", ".."))


def load_manifest(claude: Path, run: Run) -> dict[str, str]:
    path = claude / MANIFEST
    if not path.exists():
        return {}
    try:
        agents = json.loads(path.read_text(encoding="utf-8"))["agents"]
        if not isinstance(agents, dict):
            raise ValueError("agents is not an object")
        agents = {str(k): str(v) for k, v in agents.items()}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"note: ignoring unreadable manifest ({exc})")
        return {}
    good = {}
    for name, digest in agents.items():
        if valid_key(name):
            good[name] = digest
        else:
            print(f"note: ignoring unsafe manifest entry {name!r}")
    return good


def write_manifest(claude: Path, agents: dict[str, str], run: Run) -> None:
    body = (json.dumps({"version": VERSION, "agents": dict(sorted(agents.items()))}, indent=2)
            + "\n").encode("utf-8")
    path = claude / MANIFEST
    if path.exists() and path.read_bytes() == body:
        print(f"{MANIFEST}: unchanged")
        return
    run.say(f"{MANIFEST}: written")
    if not run.dry:
        atomic_write(path, body)


def link_note(target: Path, verb: str) -> str:
    if target.is_symlink():
        return f" (symlink target {os.path.realpath(target)} {verb})"
    return ""


def backup_and_say(target: Path, run: Run) -> Path:
    bak = backup_path(target)
    if not run.dry:
        atomic_write(bak, target.read_bytes())
    return bak


def read_source(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def install_agents(claude: Path, sources: list[Path], force: bool, run: Run) -> None:
    old = load_manifest(claude, run)
    new: dict[str, str] = {}
    agents_dir = claude / "agents"
    shipped = set()
    for src in sources:
        shipped.add(src.name)
        data = read_source(src)
        digest = sha(data)
        target = agents_dir / src.name
        label = f"agents/{src.name}"
        if not target.exists():
            run.say(f"{label}: created")
            if not run.dry:
                atomic_write(target, data)
            new[src.name] = digest
            continue
        current = sha(target.read_bytes())
        if current == digest:
            print(f"{label}: unchanged")
            new[src.name] = digest
        elif old.get(src.name) == current:
            run.say(f"{label}: updated")
            if not run.dry:
                atomic_write(target, data)
            new[src.name] = digest
        elif force:
            bak = backup_and_say(target, run)
            note = link_note(target, "overwritten")
            run.say(f"{label}: replaced{note}, backup at {bak.relative_to(claude).as_posix()}")
            if not run.dry:
                atomic_write(target, data)
            new[src.name] = digest
        else:
            run.conflict(f"{label}: {SKIP_MSG}")
            if src.name in old:
                new[src.name] = old[src.name]
    for name, digest in old.items():
        if name in shipped:
            continue
        target = agents_dir / name
        label = f"agents/{name}"
        if not target.exists():
            continue
        if sha(target.read_bytes()) == digest:
            run.say(f"{label}: removed")
        elif force:
            bak = backup_and_say(target, run)
            note = link_note(target, "not touched; only the link is removed")
            run.say(f"{label}: removed{note}, backup at {bak.relative_to(claude).as_posix()}")
        else:
            run.conflict(f"{label}: no longer shipped but modified locally; left in place; "
                         "rerun with --force to remove (a backup is kept)")
            new[name] = digest
            continue
        if not run.dry:
            target.unlink()
    write_manifest(claude, new, run)


def uninstall_agents(claude: Path, force: bool, run: Run) -> None:
    old = load_manifest(claude, run)
    for name, digest in sorted(old.items()):
        target = claude / "agents" / name
        label = f"agents/{name}"
        if not target.exists():
            continue
        if sha(target.read_bytes()) == digest:
            run.say(f"{label}: removed")
        elif force:
            bak = backup_and_say(target, run)
            note = link_note(target, "not touched; only the link is removed")
            run.say(f"{label}: removed{note}, backup at {bak.relative_to(claude).as_posix()}")
        else:
            run.conflict(f"{label}: modified locally; left in place; rerun with --force to remove")
            continue
        if not run.dry:
            target.unlink()
    manifest = claude / MANIFEST
    if manifest.exists():
        run.say(f"{MANIFEST}: removed")
        if not run.dry:
            manifest.unlink()


def find_markers(text: str):
    """Return (begins, ends) as lists of (start, end_including_eol), skipping fenced code."""
    begins, ends = [], []
    fence = None  # (char, length)
    for m in re.finditer(r"[^\n]*\n|[^\n]+", text):
        raw = m.group(0)
        content = raw.rstrip("\n").rstrip("\r")
        fm = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", content)
        if fence is None:
            if fm and not (fm.group(1)[0] == "`" and "`" in fm.group(2)):
                fence = (fm.group(1)[0], len(fm.group(1)))
                continue
        else:
            if fm and fm.group(1)[0] == fence[0] and len(fm.group(1)) >= fence[1] \
                    and not fm.group(2).strip():
                fence = None
            continue
        marker = content.rstrip(" \t")
        if marker.startswith(" "):
            stripped = marker.lstrip(" ")
            marker = stripped if len(marker) - len(stripped) <= 3 else marker
        if marker == BEGIN:
            begins.append((m.start(), m.end()))
        elif marker == END:
            ends.append((m.start(), m.end()))
    if fence is not None:
        raise ValueError("unclosed code fence in CLAUDE.md; "
                         "cannot locate claude-agent-ladder markers safely")
    return begins, ends


def block_span(text: str):
    """Return (start, end) of the block, None if absent, or raise ValueError if malformed."""
    begins, ends = find_markers(text)
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1 or ends[0][0] < begins[0][1]:
        raise ValueError(f"malformed claude-agent-ladder markers ({len(begins)} begin, {len(ends)} end, "
                         "expected one of each in order)")
    return begins[0][0], ends[0][1]


def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def read_claude_md(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return read_text(path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"CLAUDE.md: cannot read as UTF-8 ({exc}); nothing changed")


def parse_span(text: str):
    try:
        return block_span(text)
    except ValueError as exc:
        raise ValueError(f"CLAUDE.md rules block: {exc}; nothing changed")


def build_block(rules: str, nl: str) -> str:
    body = rules.replace("\r\n", "\n").replace("\r", "\n")
    for line in body.split("\n"):
        if line.rstrip(" \t") in (BEGIN, END):
            raise ValueError("rules.md contains an claude-agent-ladder marker line; nothing changed")
    if not body.endswith("\n"):
        body += "\n"
    return (BEGIN + "\n" + body + END + "\n").replace("\n", nl)


def plan_rules_install(claude: Path, rules_src: Path):
    """Return (status, new_text). Raises ValueError before anything is written."""
    text = read_claude_md(claude / "CLAUDE.md")
    nl = "\r\n" if "\r\n" in text else "\n"
    try:
        rules = read_text(rules_src)
    except (OSError, ValueError) as exc:
        raise ValueError(f"rules.md: cannot read ({exc}); nothing changed")
    block = build_block(rules, nl)
    span = parse_span(text)
    if span is None:
        if text:
            if not text.endswith("\n"):
                text += nl
            text += nl
        return "created", text + block
    result = text[:span[0]] + block + text[span[1]:]
    return ("unchanged" if result == text else "updated"), result


def plan_rules_uninstall(claude: Path):
    """Return new text or None when there is nothing to remove."""
    path = claude / "CLAUDE.md"
    if not path.exists():
        return None
    text = read_claude_md(path)
    span = parse_span(text)
    if span is None:
        return None
    before = text[:span[0]]
    for sep in ("\r\n\r\n", "\n\n"):
        if before.endswith(sep):
            before = before[:-(len(sep) // 2)]
            break
    return before + text[span[1]:]


def plan_settings(claude: Path, size: str):
    path = claude / "settings.json"
    try:
        data = json.loads(read_text(path)) if path.exists() else {}
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
    except (ValueError, OSError) as exc:
        raise ValueError(f"settings.json: cannot parse ({exc}); nothing changed")
    data["workflowSizeGuideline"] = size
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def parse_args(argv):
    p = argparse.ArgumentParser(description="Install claude-agent-ladder subagents and routing rules.")
    p.add_argument("--claude-dir", type=Path, default=None,
                   help="Claude config dir (default: $CLAUDE_CONFIG_DIR or ~/.claude)")
    p.add_argument("--uninstall", action="store_true", help="remove what this installer manages")
    p.add_argument("--dry-run", action="store_true", help="print actions without writing")
    p.add_argument("--force", action="store_true", help="replace/remove locally modified agents (backup kept)")
    p.add_argument("--workflow-size", choices=SIZES, default=None,
                   help="set workflowSizeGuideline in settings.json")
    p.add_argument("--no-rules", action="store_true", help="skip the CLAUDE.md rules block")
    return p.parse_args(argv)


def execute(args, claude: Path, run: Run) -> None:
    if args.uninstall:
        try:
            rules_new = None if args.no_rules else plan_rules_uninstall(claude)
        except ValueError as exc:
            run.error(str(exc))
            return
        uninstall_agents(claude, args.force, run)
        if rules_new is not None:
            run.say("CLAUDE.md rules block: removed")
            if not run.dry:
                atomic_write(claude / "CLAUDE.md", rules_new.encode("utf-8"))
        print("settings.json workflowSizeGuideline: left as is")
        return
    sources = sorted((ROOT / "subagents").glob("*.md"))
    rules_src = ROOT / "rules.md"
    if not sources or (not args.no_rules and not rules_src.is_file()):
        run.error("missing source files (subagents/*.md or rules.md)")
        return
    try:
        status, rules_new = (None, None) if args.no_rules else plan_rules_install(claude, rules_src)
        settings_new = plan_settings(claude, args.workflow_size) if args.workflow_size else None
    except ValueError as exc:
        run.error(str(exc))
        return
    install_agents(claude, sources, args.force, run)
    if status == "unchanged":
        print("CLAUDE.md rules block: unchanged")
    elif status:
        run.say(f"CLAUDE.md rules block: {status}")
        if not run.dry:
            atomic_write(claude / "CLAUDE.md", rules_new.encode("utf-8"))
    if settings_new is not None:
        run.say(f"settings.json workflowSizeGuideline: {args.workflow_size}")
        if not run.dry:
            atomic_write(claude / "settings.json", settings_new)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.claude_dir is not None:
        claude = args.claude_dir
    else:
        env = os.environ.get("CLAUDE_CONFIG_DIR")
        claude = Path(env) if env else Path.home() / ".claude"
    claude = claude.expanduser()
    run = Run(args.dry_run)
    try:
        execute(args, claude, run)
    except Exception as exc:  # last resort: exit 1 must mean conflicts only
        run.error(f"{type(exc).__name__}: {exc}")
    if run.errors:
        print(f"claude-agent-ladder {VERSION}: failed")
        return 2
    if run.conflicts:
        print(f"claude-agent-ladder {VERSION}: done with conflicts")
        return 1
    print(f"claude-agent-ladder {VERSION}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
