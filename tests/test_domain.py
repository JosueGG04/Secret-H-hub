"""The rules every score in the app is derived from."""

import pytest

from secret_hitler.domain import (
    ROLES, WIN_CONDITIONS, condition_label, role_faction,
)


@pytest.mark.parametrize("role, faction", [
    ("Liberal", "Liberal"),
    ("Fascist", "Fascist"),
    ("Hitler", "Fascist"),        # Hitler scores as a Fascist
])
def test_role_faction(role, faction):
    assert role_faction(role) == faction


def test_every_role_maps_to_a_faction():
    assert {role_faction(r) for r in ROLES} == {"Liberal", "Fascist"}


def test_every_win_condition_names_a_real_faction():
    for key, meta in WIN_CONDITIONS.items():
        assert meta["faction"] in ("Liberal", "Fascist"), key
        assert meta["label"]


def test_both_factions_can_win():
    factions = {m["faction"] for m in WIN_CONDITIONS.values()}
    assert factions == {"Liberal", "Fascist"}


def test_condition_label_falls_back_to_the_raw_key():
    assert condition_label("liberal_policies") == "Five Liberal policies enacted"
    assert condition_label("who_knows") == "who_knows"
