from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from yellow_sleeper.config import DynamicPolicy, IdentityConfigError, load_config
from yellow_sleeper.models import PolicyOverride


def test_dynamic_policy_rejects_non_lists() -> None:
    try:
        DynamicPolicy.model_validate({"hard_untouchables": "Example Franchise Quarterback"})
    except ValueError as exc:
        assert "policy fields must be lists" in str(exc)
    else:
        raise AssertionError("DynamicPolicy accepted a non-list policy field")


def test_config_precedence_yaml_over_env_and_override_over_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / ".yellow-sleeper.yaml"
    config_path.write_text(
        "\n".join(
            [
                "hard_untouchables:",
                "  - Example Franchise Quarterback",
                "protected_players:",
                "  - Example Young Wide Receiver",
                "sleeper_username: yaml_casey",
                "sleeper_league_id: '1111111111'",
                "tep_tier: te++",
            ]
        ),
        encoding="utf-8",
    )
    env = {
        "SLEEPER_USERNAME": "env_casey",
        "SLEEPER_LEAGUE_ID": "2222222222",
        "YELLOW_SLEEPER_TEP_TIER": "off",
        "YELLOW_SLEEPER_HARD_UNTOUCHABLES": "Env Only Player",
        "YELLOW_SLEEPER_PROTECTED_PICK_PATTERNS": "2029 1st",
    }

    config = load_config(env=env, config_path=config_path)

    assert config.static.sleeper_username == "yaml_casey"
    assert config.static.sleeper_league_id == "1111111111"
    assert config.static.tep_tier == "te++"
    policy, sources = config.policy()
    assert policy.hard_untouchables == ["Example Franchise Quarterback"]
    assert policy.protected_pick_patterns == ["2029 1st"]
    assert sources == [".yellow-sleeper.yaml", "env"]

    policy, sources = config.policy(
        PolicyOverride(hard_untouchables=["Tool Override Player"], protected_players=None)
    )
    assert policy.hard_untouchables == ["Tool Override Player"]
    assert policy.protected_players == ["Example Young Wide Receiver"]
    assert sources[0] == "tool_argument"


def test_config_reload_failure_preserves_previous_policy(tmp_path: Path) -> None:
    config_path = tmp_path / ".yellow-sleeper.yaml"
    config_path.write_text(
        "hard_untouchables:\n  - Example Franchise Quarterback\n", encoding="utf-8"
    )
    config = load_config(env={}, config_path=config_path)
    assert config.policy()[0].hard_untouchables == ["Example Franchise Quarterback"]

    config_path.write_text("hard_untouchables: Example Franchise Quarterback\n", encoding="utf-8")
    future = time.time() + 2
    os.utime(config_path, (future, future))

    policy, sources = config.policy()

    assert policy.hard_untouchables == ["Example Franchise Quarterback"]
    assert sources[0] == ".yellow-sleeper.yaml (reload failed, using previous)"


def test_missing_identity_is_actionable(tmp_path: Path) -> None:
    config = load_config(env={"CACHE_DIR": str(tmp_path)}, config_path=tmp_path / "missing.yaml")
    assert config.has_identity() is False
    message = config.identity_error()
    assert message is not None
    assert "sleeper_league_id" in message
    assert "sleeper_username" in message
    assert "first roster" in message
    with pytest.raises(IdentityConfigError, match="SLEEPER_LEAGUE_ID"):
        config.require_identity()


@pytest.mark.parametrize(
    ("league_id", "username"),
    [
        ("0", "casey"),
        ("your_league_id", "casey"),
        ("changeme", "casey"),
        ("1234567890", "your_username"),
        ("1234567890", "changeme"),
        ("", "casey"),
        ("1234567890", ""),
    ],
)
def test_sentinel_identity_is_rejected(tmp_path: Path, league_id: str, username: str) -> None:
    env = {
        "SLEEPER_LEAGUE_ID": league_id,
        "SLEEPER_USERNAME": username,
        "CACHE_DIR": str(tmp_path),
    }
    config = load_config(env=env, config_path=tmp_path / "missing.yaml")
    assert config.has_identity() is False


def test_explicit_identity_is_required_and_accepted(tmp_path: Path) -> None:
    env = {
        "SLEEPER_LEAGUE_ID": "1234567890",
        "SLEEPER_USERNAME": "casey",
        "CACHE_DIR": str(tmp_path),
    }
    config = load_config(env=env, config_path=tmp_path / "missing.yaml")
    assert config.has_identity() is True
    config.require_identity()
    assert config.static_sources == ["env"]
