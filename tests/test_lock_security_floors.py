from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

# GHSA-ffc3-869f-jxw9 (PyJWT, Dependabot #36/#44)
# GHSA-6q48-6c7w-9gw2 (certifi, Dependabot #45)
_ROOT = Path(__file__).resolve().parents[1]


def _locked_versions(name: str) -> list[tuple[int, ...]]:
    with (_ROOT / "uv.lock").open("rb") as lock_file:
        packages = tomllib.load(lock_file)["package"]
    versions = [
        tuple(int(part) for part in package["version"].split("."))
        for package in packages
        if package["name"] == name
    ]
    assert versions, f"uv.lock has no [[package]] named {name}"
    return versions


@pytest.mark.parametrize(
    ("name", "floor"),
    [
        ("pyjwt", (2, 14, 0)),
        ("certifi", (2026, 10, 18)),
    ],
)
def test_lock_security_floor(name: str, floor: tuple[int, ...]) -> None:
    for version in _locked_versions(name):
        assert version >= floor
