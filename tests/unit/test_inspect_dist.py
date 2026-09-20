from __future__ import annotations

from scripts.inspect_dist import is_forbidden_private_config, is_license_notice_member


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


def test_inspect_dist_treats_license_and_notice_as_copyright_allowlist() -> None:
    assert is_license_notice_member("LICENSE") is True
    assert is_license_notice_member("yellow_sleeper-0.1.0/LICENSE") is True
    assert is_license_notice_member("yellow_sleeper-0.1.0.dist-info/licenses/LICENSE") is True
    assert is_license_notice_member("NOTICE") is True
    assert is_license_notice_member("NOTICE.txt") is True
    assert is_license_notice_member("README.md") is False
    assert is_license_notice_member("src/yellow_sleeper/config.py") is False
