from __future__ import annotations

from yellow_sleeper.clients.fantasycalc import (
    QUERY_PARAMS,
    build_query_params,
    tep_source_explanation,
)


def test_build_query_params_default_includes_tep_te_plus() -> None:
    params = build_query_params("te+")
    assert params["tep"] == "te+"
    assert params["isDynasty"] == "true"
    assert params["numQbs"] == "2"
    assert params["numTeams"] == "14"
    assert params["ppr"] == "1"


def test_build_query_params_off_omits_tep() -> None:
    params = build_query_params("off")
    assert "tep" not in params


def test_build_query_params_te_plus_plus() -> None:
    assert build_query_params("te++")["tep"] == "te++"


def test_module_query_params_default_is_te_plus() -> None:
    assert QUERY_PARAMS["tep"] == "te+"


def test_tep_source_explanation_mentions_discrete_tier() -> None:
    text = tep_source_explanation("te+")
    assert "te+" in text
    assert "0.5" in text
