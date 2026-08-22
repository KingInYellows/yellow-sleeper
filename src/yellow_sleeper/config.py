from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .models.trade import PolicyOverride

logger = logging.getLogger("yellow_sleeper.config")

TepTier = Literal["off", "te+", "te++"]
OverlayPrecedence = Literal["overlay_wins", "blend", "fc_wins"]


class StaticConfig(BaseModel):
    sleeper_league_id: str = Field("0", max_length=20)
    sleeper_username: str = Field("brad", max_length=100)
    league_format: str = "14-team SF PPR 0.5 TEP"
    cache_dir: Path = Path(".cache")
    tep_tier: TepTier = "te+"
    values_overlay_path: Path | None = None
    overlay_precedence: OverlayPrecedence = "overlay_wins"
    overlay_disagreement_pct: float = Field(10.0, ge=0.0, le=100.0)


class DynamicPolicy(BaseModel):
    hard_untouchables: list[str] = Field(default_factory=list)
    protected_players: list[str] = Field(default_factory=list)
    protected_pick_patterns: list[str] = Field(default_factory=list)

    @field_validator(
        "hard_untouchables",
        "protected_players",
        "protected_pick_patterns",
        mode="before",
    )
    @classmethod
    def _validate_policy_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("policy fields must be lists")
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("policy entries must be strings")
            stripped = item.strip()
            if not stripped:
                raise ValueError("policy entries must not be empty")
            cleaned.append(stripped)
        return cleaned


class Config:
    def __init__(
        self,
        static: StaticConfig,
        policy: DynamicPolicy,
        yaml_path: Path,
        *,
        policy_sources: list[str] | None = None,
        static_sources: list[str] | None = None,
        env_policy: DynamicPolicy | None = None,
    ) -> None:
        self.static = static
        self._policy = policy
        self._yaml_path = yaml_path
        self._policy_sources = policy_sources or ["built-in_default"]
        self.static_sources = static_sources or ["built-in_default"]
        self._env_policy = env_policy
        self._policy_mtime = yaml_path.stat().st_mtime if yaml_path.exists() else 0.0

    def policy(self, override: PolicyOverride | None = None) -> tuple[DynamicPolicy, list[str]]:
        sources = list(self._policy_sources)
        if self._yaml_path.exists():
            mtime = self._yaml_path.stat().st_mtime
            if mtime != self._policy_mtime:
                try:
                    yaml_policy, yaml_sources = _load_yaml_policy(
                        self._yaml_path, env_policy=self._env_policy
                    )
                    if self._env_policy is not None and self._env_policy.model_dump(
                        exclude_defaults=True
                    ):
                        yaml_sources = yaml_sources + ["env"]
                    self._policy = yaml_policy
                    self._policy_sources = yaml_sources
                    self._policy_mtime = mtime
                    sources = [f"{yaml_sources[0]} (reloaded)", *yaml_sources[1:]]
                except (ValidationError, YAMLError, OSError, ValueError) as exc:
                    logger.warning(
                        "policy hot-reload failed for %s: %s",
                        self._yaml_path,
                        exc,
                        exc_info=True,
                    )
                    sources = [".yellow-sleeper.yaml (reload failed, using previous)", *sources]
            elif ".yellow-sleeper.yaml" not in sources:
                sources.insert(0, ".yellow-sleeper.yaml")

        effective = self._policy
        if override is not None:
            effective = _merge_policy(effective, override)
            sources.insert(0, "tool_argument")
        return effective, sources


def load_config(
    *,
    env: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> Config:
    env = env or os.environ
    yaml_path = config_path or Path(env.get("YELLOW_SLEEPER_CONFIG", ".yellow-sleeper.yaml"))
    yaml_data = _read_yaml_mapping(yaml_path)

    static, static_sources = _load_static_config(env, yaml_data)
    env_policy, env_sources = _load_env_policy(env)

    if yaml_path.exists():
        yaml_policy, yaml_sources = _load_yaml_policy(yaml_path, env_policy=env_policy)
        policy = yaml_policy
        policy_sources = yaml_sources + env_sources
    else:
        policy = env_policy
        policy_sources = env_sources or ["built-in_default"]

    return Config(
        static=static,
        policy=policy,
        yaml_path=yaml_path,
        policy_sources=policy_sources,
        static_sources=static_sources,
        env_policy=env_policy,
    )


def _load_static_config(
    env: Mapping[str, str],
    yaml_data: Mapping[str, Any],
) -> tuple[StaticConfig, list[str]]:
    values: dict[str, Any] = {}
    sources: list[str] = []

    yaml_keys = {
        "sleeper_league_id": "sleeper_league_id",
        "sleeper_username": "sleeper_username",
        "league_format": "league_format",
        "cache_dir": "cache_dir",
        "tep_tier": "tep_tier",
        "values_overlay_path": "values_overlay_path",
        "overlay_precedence": "overlay_precedence",
        "overlay_disagreement_pct": "overlay_disagreement_pct",
    }
    for yaml_key, model_key in yaml_keys.items():
        if yaml_key in yaml_data:
            values[model_key] = yaml_data[yaml_key]
            if ".yellow-sleeper.yaml" not in sources:
                sources.append(".yellow-sleeper.yaml")

    env_keys = {
        "SLEEPER_LEAGUE_ID": "sleeper_league_id",
        "SLEEPER_USERNAME": "sleeper_username",
        "LEAGUE_FORMAT": "league_format",
        "CACHE_DIR": "cache_dir",
        "YELLOW_SLEEPER_TEP_TIER": "tep_tier",
        "YELLOW_SLEEPER_VALUES_OVERLAY_PATH": "values_overlay_path",
        "YELLOW_SLEEPER_OVERLAY_PRECEDENCE": "overlay_precedence",
        "YELLOW_SLEEPER_OVERLAY_DISAGREEMENT_PCT": "overlay_disagreement_pct",
    }
    for env_key, model_key in env_keys.items():
        if model_key not in values and env_key in env:
            values[model_key] = env[env_key]
            if "env" not in sources:
                sources.append("env")

    if not sources:
        sources.append("built-in_default")
    return StaticConfig.model_validate(values), sources


def _load_env_policy(env: Mapping[str, str]) -> tuple[DynamicPolicy, list[str]]:
    keys = {
        "YELLOW_SLEEPER_HARD_UNTOUCHABLES": "hard_untouchables",
        "YELLOW_SLEEPER_PROTECTED_PLAYERS": "protected_players",
        "YELLOW_SLEEPER_PROTECTED_PICK_PATTERNS": "protected_pick_patterns",
    }
    values: dict[str, list[str]] = {}
    for env_key, model_key in keys.items():
        raw = env.get(env_key)
        if raw:
            values[model_key] = [part.strip() for part in raw.split(",") if part.strip()]
    sources = ["env"] if values else []
    return DynamicPolicy.model_validate(values), sources


def _load_yaml_policy(
    yaml_path: Path,
    *,
    env_policy: DynamicPolicy | None = None,
) -> tuple[DynamicPolicy, list[str]]:
    yaml_data = _read_yaml_mapping(yaml_path)
    policy_data = yaml_data.get("policy_override", yaml_data)
    if not isinstance(policy_data, Mapping):
        raise ValueError("policy_override must be a mapping")

    base = env_policy.model_dump() if env_policy else {}
    for key in ("hard_untouchables", "protected_players", "protected_pick_patterns"):
        if key in policy_data:
            base[key] = policy_data[key]
    return DynamicPolicy.model_validate(base), [".yellow-sleeper.yaml"]


def _read_yaml_mapping(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    yaml = YAML(typ="safe")
    data = yaml.load(path) or {}
    if not isinstance(data, Mapping):
        raise ValueError("config YAML must be a mapping")
    return data


def _merge_policy(base: DynamicPolicy, override: PolicyOverride) -> DynamicPolicy:
    data = base.model_dump()
    override_data = override.model_dump(exclude_none=True)
    data.update(override_data)
    return DynamicPolicy.model_validate(data)
