#!/usr/bin/env python3
"""Install only the ladder's resources, profiles, and marked guidance. Python 3.11+."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import tomllib
import uuid

NAME = "codex-agent-ladder"
BEGIN = f"<!-- {NAME}:begin -->"
END = f"<!-- {NAME}:end -->"
PROFILES = ("ladder-scout", "ladder-worker", "ladder-deep-worker", "ladder-verifier")
# SHA-256 of the normalized files shipped before roles became unpinned.
LEGACY_INSTALLERS = {
    "859e233d88c561482159a1573605f7d57ca3711df50a5df45b19b909cdbc1c54",  # 1132d1d
    "d3ac30697cc0e6a6ed31bfa7fe9d592a889b106a7687b12cdaf41f453dbb9185",  # 958dcc9
    "ae6a27b3a3e645c4d80f4563d9370b539c3379a690888457531a2af442679f91",  # f9b0a68
}
LEGACY_ROLES = {
    "4a9609f0c7762ec228a116fb3494736e3714a07250b8ef254821853bce1d7e23",  # ladder-deep-worker at 1132d1d
    "e94631539aa7245f2e86686b23e0242ab5206f130a88217bbb067617ef2747bd",  # ladder-scout at 1132d1d
    "619b59160c4c97eea2df1fd99c9836eb18e26251316be02640b69458d3b9587b",  # ladder-scout at 958dcc9
    "df66f198023c7682c17a70de8fb8a558b868b33010f66c86f2551cb1613de198",  # ladder-verifier at 1132d1d
    "763e0a31ae465f6d5d50bae8489089f4e7d54cb2ad46fd7d0f00b16589734f39",  # ladder-verifier at 958dcc9
    "173bc98000024ae77f4ad98efa1932569f6c26a275211113258d0e54579c0cb5",  # ladder-worker at 1132d1d
}
RESOURCES = (
    "SKILL.md", "agents/openai.yaml", "references/installation.md",
    "scripts/install.py", "assets/routing.md",
    *(f"assets/subagents/{name}.toml" for name in PROFILES),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def block_digest(text: str) -> str:
    return digest(normalized(text).strip("\n").encode("utf-8"))


@dataclass
class Layout:
    root: Path
    codex: Path
    skill: Path
    guidance: Path

    @classmethod
    def make(cls, codex_dir: str | None, project: str | None) -> Layout:
        if project:
            root = Path(project).expanduser().resolve()
            if not root.is_dir():
                raise ValueError("--project must name an existing directory")
            return cls(root, root / ".codex", root / ".agents/skills" / NAME, root)
        configured = codex_dir or os.environ.get("CODEX_HOME")
        root = Path(configured).expanduser().resolve() if configured else (Path.home() / ".codex").resolve()
        if root == Path(root.anchor):
            raise ValueError("The Codex directory cannot be a filesystem root")
        return cls(root, root, root / "skills" / NAME, root)

    def key(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def check(self, path: Path) -> None:
        """Check the lexical boundary and every destination component before writing."""
        path.relative_to(self.root)
        current = path
        while current != self.root:
            try:
                attributes = current.lstat()
            except FileNotFoundError:
                attributes = None
            is_link = attributes is not None and (
                stat.S_ISLNK(attributes.st_mode)
                or getattr(attributes, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            )
            if is_link:
                raise ValueError(f"Refusing destination link or junction: {current}")
            current = current.parent
        if not path.resolve().is_relative_to(self.root):
            raise ValueError(f"Destination escapes the selected directory: {path}")
        if path.exists() and not path.is_file():
            raise ValueError(f"Expected a file: {path}")

    def desired(self, source: Path) -> dict[Path, bytes]:
        files = {}
        for relative in RESOURCES:
            original = source / relative
            if not original.is_file() or original.is_symlink():
                raise ValueError(f"Missing or linked package resource: {original}")
            files[self.skill / relative] = normalized(original.read_text(encoding="utf-8-sig")).encode("utf-8")
        for name in PROFILES:
            data = files[self.skill / f"assets/subagents/{name}.toml"]
            profile = tomllib.loads(data.decode("utf-8"))
            if profile.get("name") != name.replace("-", "_"):
                raise ValueError(f"Invalid profile name: {name}")
            for key in ("description", "developer_instructions"):
                if not isinstance(profile.get(key), str) or not profile[key].strip():
                    raise ValueError(f"Missing {key} in {name}")
            if "model" in profile and (not isinstance(profile["model"], str) or not profile["model"].strip()):
                raise ValueError(f"Invalid model in {name}")
            if "model_reasoning_effort" in profile and profile["model_reasoning_effort"] not in (
                "low", "medium", "high", "xhigh", "max", "ultra",
            ):
                raise ValueError(f"Invalid reasoning effort in {name}")
            if "sandbox_mode" in profile or "approval_policy" in profile:
                raise ValueError(f"Configure permissions on the parent session, not profile {name}")
            files[self.codex / "agents" / f"{name}.toml"] = data
        for path in files:
            self.check(path)
        return files

    def removal_targets(self) -> dict[Path, bytes]:
        # Uninstall may run from its own partially removed or customized package.
        # Its allowlist must not depend on the contents of those source files.
        paths = [self.skill / relative for relative in RESOURCES]
        paths.extend(self.codex / "agents" / f"{name}.toml" for name in PROFILES)
        for path in paths:
            self.check(path)
        return dict.fromkeys(paths, b"")


def bounds(text: str) -> tuple[int, int] | None:
    """Require exactly one whole-line marker pair outside balanced code fences."""
    markers = []
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip().lstrip("\ufeff")
        match = re.match(r"^(`{3,}|~{3,})(.*)$", stripped)
        if match:
            token, suffix = match.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not suffix.strip():
                fence = None
        if stripped in {BEGIN, END}:
            if fence is not None:
                raise ValueError("Routing markers cannot be inside a code fence")
            markers.append((stripped, offset, offset + len(line.rstrip("\r\n"))))
        elif BEGIN in line or END in line:
            raise ValueError("Routing markers must be on their own lines")
        offset += len(line)
    if fence is not None:
        raise ValueError("Guidance contains an unclosed code fence")
    if not markers:
        return None
    if len(markers) != 2 or markers[0][0] != BEGIN or markers[1][0] != END:
        raise ValueError("Malformed or duplicate routing markers")
    return markers[0][1], markers[1][2]


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8") if path.exists() else ""


def active_guidance(layout: Layout) -> Path:
    override = layout.guidance / "AGENTS.override.md"
    layout.check(override)
    return override if read_text(override).lstrip("\ufeff").strip() else layout.guidance / "AGENTS.md"


def load_manifest(path: Path, layout: Layout, desired: dict[Path, bytes]) -> dict:
    layout.check(path)
    if not path.exists():
        return {"schema": 1, "files": {}, "rules": None, "legacy_profiles": []}
    return validate_manifest(json.loads(read_text(path).lstrip("\ufeff")), layout, desired)


def validate_manifest(record: dict, layout: Layout, desired: dict[Path, bytes]) -> dict:
    if not isinstance(record, dict) or record.get("schema") != 1 or not isinstance(record.get("files"), dict):
        raise ValueError("Invalid ladder manifest")
    allowed = {layout.key(p) for p in desired}
    valid_hash = lambda value: isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
    for key, value in record["files"].items():
        if key not in allowed or not valid_hash(value):
            raise ValueError(f"Invalid manifest entry: {key}")
        layout.check(layout.root / key)
    # A legacy installer owned released profile bytes. A newer installer may
    # have installed those exact bytes from an explicitly pinned source bundle.
    legacy = record.get("legacy_profiles")
    if "legacy_profiles" not in record:
        script = layout.skill / "scripts/install.py"
        installer_hash = record["files"].get(layout.key(script))
        record["legacy_profiles"] = [
            key for key, checksum in record["files"].items()
            if installer_hash in LEGACY_INSTALLERS and checksum in LEGACY_ROLES
        ]
    elif (not isinstance(legacy, list) or
          any(not isinstance(key, str) or record["files"].get(key) not in LEGACY_ROLES for key in legacy)):
        raise ValueError("Invalid legacy profile entry")
    rules = record.get("rules")
    if rules is not None:
        allowed_rules = {layout.key(layout.guidance / name) for name in ("AGENTS.md", "AGENTS.override.md")}
        if not isinstance(rules, dict) or rules.get("path") not in allowed_rules or not valid_hash(rules.get("sha256")):
            raise ValueError("Invalid routing manifest entry")
        layout.check(layout.root / rules["path"])
    return record


def recover_ownership(journal: Path, manifest: Path, layout: Layout,
                      desired: dict[Path, bytes]) -> None:
    """Recover ownership only; never replay writes over user files."""
    record = json.loads(read_text(journal))
    if not isinstance(record, dict) or record.get("schema") != 1:
        raise ValueError("Invalid ladder transaction journal")
    before = validate_manifest(record.get("before"), layout, desired)
    after = validate_manifest(record.get("after"), layout, desired)
    owned = {}
    legacy = []
    for key in before["files"].keys() | after["files"].keys():
        path = layout.root / key
        if not path.exists():
            continue
        current = digest(path.read_bytes())
        # Keep the previous owner for incomplete updates. Subsequent edits stay
        # protected because their bytes differ from the recorded ownership hash.
        owner = after if current == after["files"].get(key) or key not in before["files"] else before
        owned[key] = owner["files"][key]
        if key in owner["legacy_profiles"]:
            legacy.append(key)
    old_rules, new_rules = before.get("rules"), after.get("rules")
    rules = old_rules or new_rules
    if rules:
        text = read_text(layout.root / rules["path"])
        span = bounds(text)
        if span is None:
            rules = None
        elif new_rules and block_digest(text[slice(*span)]) == new_rules["sha256"]:
            rules = new_rules
    recovered = {"schema": 1, "files": owned, "rules": rules, "legacy_profiles": sorted(legacy)}
    if owned or rules:
        write_atomic(manifest, (json.dumps(recovered, indent=2, sort_keys=True) + "\n").encode())
    else:
        manifest.unlink(missing_ok=True)
    journal.unlink()
    print("recovered: ownership from interrupted operation; user files were not replayed")


@dataclass
class Change:
    path: Path
    data: bytes | None
    action: str
    backup: bool = False


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def execute(changes: list[Change], layout: Layout, dry_run: bool) -> None:
    for change in changes:
        layout.check(change.path)
        print(f"{'would ' if dry_run else ''}{change.action}: {change.path}")
        if dry_run:
            continue
        if change.backup:
            backup = change.path.with_name(f"{change.path.name}.{uuid.uuid4().hex[:12]}.bak")
            layout.check(backup)
            write_atomic(backup, change.path.read_bytes())
            print(f"backup: {backup}")
        if change.data is None:
            change.path.unlink(missing_ok=True)
        else:
            write_atomic(change.path, change.data)


def drops_custom_pins(path: Path, previous: bytes, expected: bytes) -> bool:
    if path.suffix != ".toml":
        return False
    old_profile = tomllib.loads(previous.decode("utf-8-sig"))
    new_profile = tomllib.loads(expected.decode("utf-8"))
    return any(key in old_profile and old_profile[key] != new_profile.get(key)
               for key in ("model", "model_reasoning_effort"))


def maintain(source: Path, layout: Layout, *, dry_run: bool = False, force: bool = False,
             verify: bool = False, uninstall: bool = False) -> int:
    desired = layout.removal_targets() if uninstall else layout.desired(source)
    manifest_path = layout.codex / f"{NAME}.manifest.json"
    journal_path = layout.codex / f"{NAME}.transaction.json"
    layout.check(manifest_path)
    layout.check(journal_path)
    if journal_path.exists():
        if dry_run or verify:
            print("pending interrupted operation: run install or uninstall to recover ownership")
            return 1
        recover_ownership(journal_path, manifest_path, layout, desired)
    manifest = load_manifest(manifest_path, layout, desired)
    owned = manifest["files"].copy()
    rules_record = dict(manifest["rules"]) if manifest.get("rules") else None
    guidance = layout.root / rules_record["path"] if uninstall and rules_record else active_guidance(layout)
    layout.check(guidance)
    text = read_text(guidance)
    span = bounds(text)
    expected_block = desired[layout.skill / "assets/routing.md"].decode("utf-8").rstrip("\n")
    if not uninstall and bounds(expected_block) != (0, len(expected_block)):
        raise ValueError("Invalid bundled routing block")
    present_block = text[slice(*span)] if span else None
    changes = []
    issues = []

    if verify:
        for path, expected in desired.items():
            if not path.exists() or path.read_bytes() != expected:
                issues.append(f"missing or different: {path}")
        if present_block is None or block_digest(present_block) != block_digest(expected_block):
            issues.append(f"missing or different routing block: {guidance}")
        if rules_record and rules_record["path"] != layout.key(guidance):
            issues.append("managed routing block is no longer in the active guidance file")
        for issue in issues:
            print(issue)
        if not issues:
            print("verified: installed resources, four profiles, and automatic routing match this package")
        return int(bool(issues))

    if not uninstall and rules_record and rules_record["path"] != layout.key(guidance):
        raise ValueError("Active guidance changed; uninstall the previous routing block before reinstalling")

    for path, expected in desired.items():
        key = layout.key(path)
        existing = path.read_bytes() if path.exists() else None
        managed = key in owned
        if uninstall:
            if not managed:
                continue
            if existing is None:
                owned.pop(key)
            elif digest(existing) == owned[key]:
                changes.append(Change(path, None, "remove"))
                owned.pop(key)
            else:
                issues.append(f"preserved customized file: {path}")
        elif existing == expected:
            print(f"unchanged: {path}")
            if managed:
                owned[key] = digest(expected)
        elif (existing is not None and managed and digest(existing) == owned[key]
              and key not in manifest["legacy_profiles"] and drops_custom_pins(path, existing, expected)):
            # Recovery must protect the original even if --force stops before
            # its first backup. Only the replacement bytes can be owned again.
            del manifest["files"][key]
            owned.pop(key)
            if force:
                changes.append(Change(path, expected, "replace", backup=True))
                owned[key] = digest(expected)
            else:
                issues.append(f"preserved user-pinned profile: {path}")
        elif existing is None or (managed and digest(existing) == owned[key]):
            changes.append(Change(path, expected, "create" if existing is None else "update"))
            owned[key] = digest(expected)
        elif force:
            changes.append(Change(path, expected, "replace", backup=True))
            owned[key] = digest(expected)
        else:
            issues.append(f"skipped conflicting or customized file: {path}")

    if uninstall:
        if rules_record:
            if present_block is None:
                rules_record = None
            elif block_digest(present_block) == rules_record["sha256"]:
                # Remove only the marker span. Keep every byte outside the block.
                revised = text[:span[0]] + text[span[1]:]
                changes.append(Change(guidance, revised.encode("utf-8"), "remove routing block"))
                rules_record = None
            else:
                issues.append(f"preserved customized routing block: {guidance}")
    elif present_block is None:
        newline = "\r\n" if "\r\n" in text else "\n"
        separator = "" if not text else (newline if text.endswith(("\n", "\r")) else newline * 2)
        revised = text + separator + expected_block.replace("\n", newline) + newline
        changes.append(Change(guidance, revised.encode("utf-8"), "add automatic routing"))
        rules_record = {"path": layout.key(guidance), "sha256": block_digest(expected_block)}
    elif block_digest(present_block) == block_digest(expected_block):
        print(f"unchanged routing: {guidance}")
        if rules_record:
            rules_record["sha256"] = block_digest(expected_block)
    elif (rules_record and block_digest(present_block) == rules_record["sha256"]) or force:
        newline = "\r\n" if "\r\n" in text else "\n"
        revised = text[:span[0]] + expected_block.replace("\n", newline) + text[span[1]:]
        changes.append(Change(guidance, revised.encode("utf-8"), "update automatic routing", backup=force))
        rules_record = {"path": layout.key(guidance), "sha256": block_digest(expected_block)}
    else:
        issues.append(f"skipped conflicting or customized routing block: {guidance}")

    new_manifest = {"schema": 1, "files": owned, "rules": rules_record, "legacy_profiles": []}
    if owned or rules_record:
        data = (json.dumps(new_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if not manifest_path.exists() or manifest_path.read_bytes() != data:
            changes.append(Change(manifest_path, data, "record ownership"))
    elif manifest_path.exists():
        changes.append(Change(manifest_path, None, "remove manifest"))
    for issue in issues:
        print(issue)
    if changes and not dry_run:
        # Persist ownership intent before the first resource mutation. On retry,
        # reconcile against observed bytes instead of claiming identical files
        # that predated this operation or replaying stale content over edits.
        journal = {"schema": 1, "before": manifest, "after": new_manifest}
        write_atomic(journal_path, (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode())
    execute(changes, layout, dry_run)
    if changes and not dry_run:
        journal_path.unlink()
    if not changes and not issues:
        print("no changes needed")
    return int(bool(issues))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--codex-dir", help="Personal Codex home; defaults to CODEX_HOME or ~/.codex")
    target.add_argument("--project", help="Existing repository root for a project-scoped installation")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify", action="store_true", help="Static read-only verification; no model calls")
    action.add_argument("--uninstall", action="store_true", help="Remove only unmodified managed resources")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--force", action="store_true", help="Replace conflicts with backups; install/update only")
    args = parser.parse_args(argv)
    if args.force and (args.verify or args.uninstall):
        parser.error("--force applies only to installation or updates")
    try:
        layout = Layout.make(args.codex_dir, args.project)
        return maintain(Path(__file__).resolve().parents[1], layout, dry_run=args.dry_run,
                        force=args.force, verify=args.verify, uninstall=args.uninstall)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
