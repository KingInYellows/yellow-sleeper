from __future__ import annotations

from scripts.inspect_dist import is_forbidden_private_config


def test_inspect_dist_rejects_private_config_basenames() -> None:
    assert is_forbidden_private_config(".env") is True
    assert is_forbidden_private_config("pkg/.env") is True
    assert is_forbidden_private_config(".env.production") is True
    assert is_forbidden_private_config("pkg/.env.local") is True
    assert is_forbidden_private_config(".yellow-sleeper.yaml") is True
    assert is_forbidden_private_config("pkg/.yellow-sleeper.private.yaml") is True
    assert is_forbidden_private_config(".yellow-sleeper.yaml.example") is False
    assert is_forbidden_private_config(".env.example") is False
    assert is_forbidden_private_config("league.json") is False
