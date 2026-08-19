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
                "user_id": "366494220145700864",
                "username": None,
                "display_name": "BradSchwarzkopf",
                "metadata": {"team_name": "Butt Naked Wondas"},
            }
        ],
        "rosters": [{"roster_id": 3, "owner_id": "366494220145700864"}],
    }
    assert find_roster_id_for_username(snapshot, "BradSchwarzkopf") == 3
    assert find_roster_id_for_username(snapshot, "bradschwarzkopf") == 3
    assert find_roster_id_for_username(snapshot, "366494220145700864") == 3
    assert find_roster_id_for_username(snapshot, "Butt Naked Wondas") == 3
    assert find_roster_id_for_username(snapshot, "nobody") is None
