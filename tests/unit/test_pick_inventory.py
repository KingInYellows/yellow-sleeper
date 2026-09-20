from __future__ import annotations

from yellow_sleeper.analyze import build_pick_inventory, find_roster_id_for_username


def test_find_roster_id_for_username(sleeper_snapshot: dict) -> None:
    assert find_roster_id_for_username(sleeper_snapshot, "casey") == 11


def test_pick_inventory_applies_traded_overlay(sleeper_snapshot: dict) -> None:
    inventory = build_pick_inventory(
        sleeper_snapshot,
        my_roster_id=11,
        seasons=[2027, 2028],
        include_traded_away=True,
    )

    owned_tokens = {pick.pick_token for pick in inventory.owned_picks}
    away_tokens = {pick.pick_token for pick in inventory.traded_away_picks}

    assert "pick_2027_r1_orig3" in owned_tokens
    assert "pick_2027_r1_orig11" in owned_tokens
    assert "pick_2028_r1_orig4" in owned_tokens
    assert "pick_2027_r2_orig11" not in owned_tokens
    assert "pick_2027_r2_orig11" in away_tokens
    assert inventory.unresolved == []


def test_list_traded_picks_are_enriched(sleeper_snapshot: dict) -> None:
    inventory = build_pick_inventory(sleeper_snapshot, my_roster_id=11, seasons=[2027])

    traded = {pick.pick_token: pick for pick in inventory.traded_picks}

    assert traded["pick_2027_r1_orig3"].original_owner_name == "Mike Johnson"
    assert traded["pick_2027_r1_orig3"].current_owner_name == "Casey Quinn"
