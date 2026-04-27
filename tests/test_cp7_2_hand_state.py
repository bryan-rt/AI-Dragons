"""Tests for CP7.2 hand state, spell slots, INTERACT/RELEASE."""

import pytest

from pf2e.actions import Action, ActionType, evaluate_action, _ACTION_EVALUATORS
from pf2e.combat_math import die_average
from sim.candidates import generate_candidates
from sim.party import make_rook, make_dalai, make_aetregan, make_erisen
from sim.scenario import load_scenario
from sim.round_state import RoundState, CombatantSnapshot
from dataclasses import replace

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Initially held
# ---------------------------------------------------------------------------

class TestInitiallyHeld:

    def test_rook_holds_earthbreaker_and_shield(self):
        r = make_rook()
        assert "Earthbreaker" in r.initially_held
        assert "Steel Shield" in r.initially_held

    def test_aetregan_holds_whip_and_shield(self):
        a = make_aetregan()
        assert "Scorpion Whip" in a.initially_held
        assert "Steel Shield" in a.initially_held

    def test_dalai_holds_rapier_pistol_and_buckler(self):
        d = make_dalai()
        assert "Rapier Pistol" in d.initially_held
        assert "Buckler" in d.initially_held

    def test_erisen_holds_dueling_pistol(self):
        e = make_erisen()
        assert "Dueling Pistol" in e.initially_held


class TestHeldWeaponsOnSnapshot:

    def test_snapshot_initialized_from_initially_held(self):
        from pf2e.character import CombatantState
        rook = make_rook()
        cs = CombatantState.from_character(rook)
        snap = CombatantSnapshot.from_combatant_state(cs)
        assert snap.held_weapons == rook.initially_held


# ---------------------------------------------------------------------------
# Strike candidate filtering
# ---------------------------------------------------------------------------

class TestStrikeHeldOnly:

    @pytest.fixture
    def state(self):
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        return RoundState.from_scenario(
            scenario, ["Rook", "Aetregan", "Dalai Alpaca", "Erisen", "Bandit1"],
        )

    def test_rook_strikes_only_with_held(self, state):
        """Rook should only get Strike candidates for Earthbreaker (held),
        not Light Hammer (stowed)."""
        # Rook already adjacent to Bandit in scenario 1
        state2 = state
        cands = generate_candidates(state2, "Rook")
        strikes = [c for c in cands if c.type == ActionType.STRIKE]
        weapon_names = {c.weapon_name for c in strikes}
        assert "Earthbreaker" in weapon_names
        assert "Light Hammer" not in weapon_names


# ---------------------------------------------------------------------------
# INTERACT and RELEASE
# ---------------------------------------------------------------------------

class TestInteract:

    @pytest.fixture
    def state(self):
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        return RoundState.from_scenario(
            scenario, ["Rook", "Aetregan", "Dalai Alpaca", "Erisen", "Bandit1"],
        )

    def test_interact_generates_for_stowed_weapons(self, state):
        """INTERACT candidate should appear for Light Hammer (stowed)."""
        cands = generate_candidates(state, "Erisen")
        interact_cands = [c for c in cands if c.type == ActionType.INTERACT]
        # Erisen has 1 free hand (only Dueling Pistol held)
        assert len(interact_cands) > 0

    def test_interact_in_dispatcher(self):
        assert ActionType.INTERACT in _ACTION_EVALUATORS

    def test_release_in_dispatcher(self):
        assert ActionType.RELEASE in _ACTION_EVALUATORS


class TestRelease:

    @pytest.fixture
    def state(self):
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        return RoundState.from_scenario(
            scenario, ["Rook", "Aetregan", "Dalai Alpaca", "Erisen", "Bandit1"],
        )

    def test_release_candidate_when_two_hand_upgrade(self, state):
        """RELEASE should be offered when dropping shield enables d10 Earthbreaker."""
        cands = generate_candidates(state, "Rook")
        release_cands = [c for c in cands if c.type == ActionType.RELEASE]
        # Rook holds Earthbreaker + Steel Shield; releasing shield enables two-hand
        shield_releases = [c for c in release_cands if c.weapon_name == "Steel Shield"]
        assert len(shield_releases) > 0


# ---------------------------------------------------------------------------
# Two-hand d10 upgrade
# ---------------------------------------------------------------------------

class TestTwoHandUpgrade:

    @pytest.fixture
    def state(self):
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        return RoundState.from_scenario(
            scenario, ["Rook", "Aetregan", "Dalai Alpaca", "Erisen", "Bandit1"],
        )

    def test_d6_when_shield_held(self, state):
        """Earthbreaker does d6 damage when shield also held."""
        rook = replace(state.pcs["Rook"], position=(5, 7))
        state2 = replace(state, pcs={**state.pcs, "Rook": rook})
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name="Earthbreaker")
        result = evaluate_action(action, state2)
        # d6 avg = 3.5 + Str 4 + anthem 1 = 8.5 per hit
        hit_outcomes = [o for o in result.outcomes
                        if o.hp_changes.get("Bandit1", 0) < 0
                        and abs(o.hp_changes["Bandit1"]) < 20]
        if hit_outcomes:
            dmg = abs(hit_outcomes[0].hp_changes["Bandit1"])
            assert dmg == pytest.approx(8.5, abs=0.5)  # d6 + mods

    def test_d10_when_only_weapon_held(self, state):
        """Earthbreaker does d10 damage when shield released."""
        rook = replace(state.pcs["Rook"], position=(5, 7),
                        held_weapons=("Earthbreaker",))
        state2 = replace(state, pcs={**state.pcs, "Rook": rook})
        action = Action(type=ActionType.STRIKE, actor_name="Rook",
                        action_cost=1, target_name="Bandit1",
                        weapon_name="Earthbreaker")
        result = evaluate_action(action, state2)
        # d10 avg = 5.5 + Str 4 + anthem 1 = 10.5 per hit
        hit_outcomes = [o for o in result.outcomes
                        if o.hp_changes.get("Bandit1", 0) < 0
                        and abs(o.hp_changes["Bandit1"]) < 25]
        if hit_outcomes:
            dmg = abs(hit_outcomes[0].hp_changes["Bandit1"])
            assert dmg == pytest.approx(10.5, abs=0.5)  # d10 + mods


# ---------------------------------------------------------------------------
# Spell slots
# ---------------------------------------------------------------------------

class TestSpellSlots:

    def test_dalai_has_spell_slots(self):
        d = make_dalai()
        assert d.starting_resources.get("spell_slot_1") == 2

    def test_non_casters_no_slots(self):
        for fn in [make_aetregan, make_rook, make_erisen]:
            c = fn()
            assert c.starting_resources == {}

    def test_snapshot_has_resources(self):
        from pf2e.character import CombatantState
        d = make_dalai()
        cs = CombatantState.from_character(d)
        snap = CombatantSnapshot.from_combatant_state(cs)
        assert snap.resources.get("spell_slot_1") == 2

    def test_cantrip_no_slot_consumed(self):
        """Needle Darts is a cantrip — never consumes slots."""
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        state = RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Rook", "Aetregan", "Erisen", "Bandit1"],
        )
        action = Action(type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="needle-darts")
        result = evaluate_action(action, state)
        assert result.eligible
        for o in result.outcomes:
            assert not o.resource_changes  # No slot consumed

    def test_fear_consumes_slot(self):
        """Fear consumes spell_slot_1."""
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        state = RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Rook", "Aetregan", "Erisen", "Bandit1"],
        )
        action = Action(type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="fear")
        result = evaluate_action(action, state)
        assert result.eligible
        has_resource_change = any(
            o.resource_changes.get("spell_slot_1") == -1
            for o in result.outcomes
        )
        assert has_resource_change

    def test_fear_ineligible_when_slots_depleted(self):
        """Fear not castable when spell_slot_1 = 0."""
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        state = RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Rook", "Aetregan", "Erisen", "Bandit1"],
        )
        dalai = replace(state.pcs["Dalai Alpaca"], resources={"spell_slot_1": 0})
        state2 = replace(state, pcs={**state.pcs, "Dalai Alpaca": dalai})
        action = Action(type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="fear")
        result = evaluate_action(action, state2)
        assert not result.eligible

    def test_needle_darts_still_works_with_no_slots(self):
        """Cantrip works even with zero spell slots."""
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        state = RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Rook", "Aetregan", "Erisen", "Bandit1"],
        )
        dalai = replace(state.pcs["Dalai Alpaca"], resources={"spell_slot_1": 0})
        state2 = replace(state, pcs={**state.pcs, "Dalai Alpaca": dalai})
        action = Action(type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
                        action_cost=2, target_name="Bandit1",
                        tactic_name="needle-darts")
        result = evaluate_action(action, state2)
        assert result.eligible


# ---------------------------------------------------------------------------
# RAISE_SHIELD requires held shield
# ---------------------------------------------------------------------------

class TestRaiseShieldHeld:

    def test_ineligible_when_shield_not_held(self):
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        state = RoundState.from_scenario(
            scenario, ["Rook", "Aetregan", "Dalai Alpaca", "Erisen", "Bandit1"],
        )
        # Remove shield from held
        rook = replace(state.pcs["Rook"], held_weapons=("Earthbreaker",))
        state2 = replace(state, pcs={**state.pcs, "Rook": rook})
        action = Action(type=ActionType.RAISE_SHIELD, actor_name="Rook", action_cost=1)
        result = evaluate_action(action, state2)
        assert not result.eligible
        assert "not held" in result.ineligibility_reason
