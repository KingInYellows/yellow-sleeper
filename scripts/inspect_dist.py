#!/usr/bin/env python3
"""Fail CI if sdist/wheel contain private operator identity or secrets."""

from __future__ import annotations

import fnmatch
import sys
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_SUBSTRINGS = (
    "/Users/brad",
    "Brad Schwarzkopf",
    "BradSchwarzkopf",
    'sleeper_username="brad"',
    "sleeper_username: brad",
    "BEGIN PRIVATE",
    "AKIA",
    "ghp_",
    "xoxb-",
)

TEXT_SUFFIXES = (".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".example")
LICENSE_NOTICE_STEMS = frozenset({"license", "notice", "copying", "authors", "copyright"})
COPYRIGHT_HOLDER_NEEDLES = frozenset({"Brad Schwarzkopf"})
PRIVATE_EXACT_NAMES = frozenset(
    {".env", ".yellow-sleeper.yaml", ".yellow-sleeper.private.yaml"}
)
PRIVATE_NAME_GLOBS = (".env.*",)


def is_license_notice_member(member_name: str) -> bool:
    """LICENSE/NOTICE files may contain the copyright holder name."""
    stem = Path(member_name).name.lower().split(".")[0]
    return stem in LICENSE_NOTICE_STEMS


def is_forbidden_private_config(member_name: str) -> bool:
    base = Path(member_name).name
    if base.endswith(".example"):
        return False
    if base in PRIVATE_EXACT_NAMES:
        return True
    return any(fnmatch.fnmatch(base, pattern) for pattern in PRIVATE_NAME_GLOBS)


def _iter_members(path: Path) -> list[tuple[str, bytes]]:
    members: list[tuple[str, bytes]] = []
    if path.suffix == ".whl" or path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith("/"):
                    continue
                members.append((name, archive.read(name)))
    elif path.name.endswith(".tar.gz") or path.suffix == ".gz":
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                members.append((member.name, extracted.read()))
    return members


def _should_scan_text(member_name: str) -> bool:
    base = Path(member_name).name
    if is_license_notice_member(member_name):
        return True
    return member_name.endswith(TEXT_SUFFIXES) or base.startswith(".env")


def main() -> int:
    dist = Path("dist")
    if not dist.exists():
        print("dist/ missing", file=sys.stderr)
        return 1
    artifacts = list(dist.glob("*.whl")) + list(dist.glob("*.tar.gz"))
    if not artifacts:
        print("no wheel/sdist in dist/", file=sys.stderr)
        return 1
    failed = False
    for artifact in artifacts:
        print(f"inspect {artifact}")
        for inner, payload in _iter_members(artifact):
            if is_forbidden_private_config(inner):
                print(f"FORBIDDEN private config {artifact.name}:{inner}", file=sys.stderr)
                failed = True
            if inner.endswith("scripts/inspect_dist.py"):
                continue
            if not _should_scan_text(inner):
                continue
            text = payload.decode("utf-8", errors="replace")
            for needle in FORBIDDEN_SUBSTRINGS:
                if needle in COPYRIGHT_HOLDER_NEEDLES and is_license_notice_member(inner):
                    continue
                if needle in text:
                    print(f"FORBIDDEN {needle!r} in {artifact.name}:{inner}", file=sys.stderr)
                    failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
