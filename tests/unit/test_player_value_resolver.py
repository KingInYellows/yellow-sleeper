from __future__ import annotations

from tests.conftest import load_fixture
from yellow_sleeper.analyze.value import resolve_player_value, values_by_sleeper_id
from yellow_sleeper.models import ValueMath


def test_value_math_public_fields_are_frozen() -> None:
    assert set(ValueMath.model_fields) == {
        "send_total",
        "receive_total",
        "delta",
        "delta_pct",
        "per_asset",
        "source_disagreement",
    }


def test_resolve_player_value_uses_fantasycalc_and_tep_provenance() -> None:
    index = values_by_sleeper_id(load_fixture("fantasycalc/values_tep_teplus.json"))
    resolved = resolve_player_value("9991", index, tep_tier="te+")
    assert resolved.value == 4140
    assert resolved.effective_source == "fantasycalc"
    assert resolved.missing == ()
    assert "te+" in resolved.provenance_explanation
    assert resolved.disagreement is None


def test_resolve_player_value_xlsx_does_not_fall_back_to_fantasycalc() -> None:
    index = values_by_sleeper_id(load_fixture("fantasycalc/values_tep_teplus.json"))
    resolved = resolve_player_value("9991", index, valuation_source="xlsx")
    assert resolved.value is None
    assert resolved.effective_source == "xlsx"
    assert resolved.missing == ("xlsx",)
    assert "CSV overlay" in resolved.provenance_explanation
