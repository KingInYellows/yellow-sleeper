from __future__ import annotations

from yellow_sleeper.analyze.overlay import build_overlay
from yellow_sleeper.analyze.tep import apply_te_premium, te_multiplier, tep_explanation
from yellow_sleeper.clients.fantasycalc import FCPlayer, FCRecord


def test_te_multiplier_half_point_tep() -> None:
    assert te_multiplier(0.5) == 1.175
    assert apply_te_premium(3261, "TE", 0.5) == 3261 * 1.175
    assert apply_te_premium(8200, "WR", 0.5) == 8200
    assert apply_te_premium(None, "TE", 0.5) is None


def test_tep_explanation_mentions_formula() -> None:
    note = tep_explanation(0.5)
    assert "1.175" in note
    assert "0.5" in note


def test_overlay_applies_tep_then_user_book_wins() -> None:
    values = [
        FCRecord(
            player=FCPlayer(id=1, name="Sam LaPorta", sleeperId="9999", position="TE"),
            value=3261,
            overallRank=1,
        ),
        FCRecord(
            player=FCPlayer(id=2, name="Drake London", sleeperId="9745", position="WR"),
            value=8200,
            overallRank=2,
        ),
    ]
    overlay = build_overlay(
        values,
        {"9999": {"position": "TE"}, "9745": {"position": "WR"}},
        tep=0.5,
        user_book={"9999": {"value": 5000, "position": "TE"}},
    )
    assert overlay.display["9999"] == 5000
    assert overlay.raw_fc["9999"] == 3261
    assert overlay.display["9745"] == 8200
    assert "9999" in overlay.user_ids
    sources = overlay.sources_for("9999")
    assert [source.source for source in sources] == ["xlsx", "fantasycalc"]
