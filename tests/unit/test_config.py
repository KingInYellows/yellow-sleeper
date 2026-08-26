from __future__ import annotations

import os
import time
from pathlib import Path

from pydantic import ValidationError

from yellow_sleeper.config import DynamicPolicy, StaticConfig, load_config
from yellow_sleeper.models import PolicyOverride


def test_dynamic_policy_rejects_non_lists() -> None:
    try:
        DynamicPolicy.model_validate({"hard_untouchables": "Drake London"})
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
                "  - Drake London",
                "protected_players:",
                "  - Jayden Daniels",
                "sleeper_username: yaml_brad",
            ]
        ),
        encoding="utf-8",
    )
    env = {
        "SLEEPER_USERNAME": "env_brad",
        "YELLOW_SLEEPER_HARD_UNTOUCHABLES": "Harold Fannin",
        "YELLOW_SLEEPER_PROTECTED_PICK_PATTERNS": "2027 1st",
    }

    config = load_config(env=env, config_path=config_path)

    assert config.static.sleeper_username == "yaml_brad"
    policy, sources = config.policy()
    assert policy.hard_untouchables == ["Drake London"]
    assert policy.protected_pick_patterns == ["2027 1st"]
    assert sources == [".yellow-sleeper.yaml", "env"]

    policy, sources = config.policy(
        PolicyOverride(hard_untouchables=["Bijan Robinson"], protected_players=None)
    )
    assert policy.hard_untouchables == ["Bijan Robinson"]
    assert policy.protected_players == ["Jayden Daniels"]
    assert sources[0] == "tool_argument"


def test_config_reload_failure_preserves_previous_policy(tmp_path: Path) -> None:
    config_path = tmp_path / ".yellow-sleeper.yaml"
    config_path.write_text("hard_untouchables:\n  - Drake London\n", encoding="utf-8")
    config = load_config(env={}, config_path=config_path)
    assert config.policy()[0].hard_untouchables == ["Drake London"]

    config_path.write_text("hard_untouchables: Drake London\n", encoding="utf-8")
    future = time.time() + 2
    os.utime(config_path, (future, future))

    policy, sources = config.policy()

    assert policy.hard_untouchables == ["Drake London"]
    assert sources[0] == ".yellow-sleeper.yaml (reload failed, using previous)"


def test_config_tep_tier_from_env_and_rejects_invalid(tmp_path: Path) -> None:
    config = load_config(
        env={"YELLOW_SLEEPER_TEP_TIER": "te++"},
        config_path=tmp_path / "missing.yaml",
    )
    assert config.static.tep_tier == "te++"

    try:
        StaticConfig.model_validate({"tep_tier": "0.5"})
    except ValidationError:
        return
    raise AssertionError("StaticConfig accepted invalid tep_tier")
