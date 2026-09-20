#!/usr/bin/env python3
"""Fail CI if sdist/wheel contain private operator identity or secrets."""

from __future__ import annotations

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


def _iter_dist_text(path: Path) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    if path.suffix == ".whl" or path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith(
                    (".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".example")
                ):
                    text = archive.read(name).decode("utf-8", errors="replace")
                    hits.append((name, text))
    elif path.name.endswith(".tar.gz") or path.suffix == ".gz":
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                text = extracted.read().decode("utf-8", errors="replace")
                hits.append((member.name, text))
    return hits


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
        for inner, text in _iter_dist_text(artifact):
            if inner.endswith("scripts/inspect_dist.py"):
                continue
            for needle in FORBIDDEN_SUBSTRINGS:
                if needle in text:
                    print(f"FORBIDDEN {needle!r} in {artifact.name}:{inner}", file=sys.stderr)
                    failed = True
            if inner.endswith(".env") or inner.endswith(".yellow-sleeper.yaml"):
                print(f"FORBIDDEN private config {artifact.name}:{inner}", file=sys.stderr)
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
