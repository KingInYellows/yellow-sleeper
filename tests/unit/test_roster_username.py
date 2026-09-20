from __future__ import annotations

from yellow_sleeper.analyze.roster import find_roster_id_for_username


def test_find_roster_matches_username_case_insensitive(sleeper_snapshot: dict) -> None:
    assert find_roster_id_for_username(sleeper_snapshot, "brad") == 11
    assert find_roster_id_for_username(sleeper_snapshot, "BRAD") == 11


def test_find_roster_matches_display_name_and_team(sleeper_snapshot: dict) -> None:
    assert find_roster_id_for_username(sleeper_snapshot, "Brad Schwarzkopf") == 11
    assert find_roster_id_for_username(sleeper_snapshot, "yellow sleeper") == 11
    assert find_roster_id_for_username(sleeper_snapshot, "u11") == 11


def test_find_roster_matches_when_username_is_null() -> None:
    snapshot = {
        "users": [
            {
                "user_id": "example-user-id",
                "username": None,
                "display_name": "example_owner",
                "metadata": {"team_name": "Example Team"},
            }
        ],
        "rosters": [{"roster_id": 3, "owner_id": "example-user-id"}],
    }
    assert find_roster_id_for_username(snapshot, "example_owner") == 3
    assert find_roster_id_for_username(snapshot, "EXAMPLE_OWNER") == 3
    assert find_roster_id_for_username(snapshot, "example-user-id") == 3
    assert find_roster_id_for_username(snapshot, "Example Team") == 3
    assert find_roster_id_for_username(snapshot, "nobody") is None
