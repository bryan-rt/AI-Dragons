"""Tests for CP5.4 spell chassis — Fear, Force Barrage, Needle Darts."""

import pytest

from pf2e.actions import Action, ActionType, evaluate_spell
from pf2e.combat_math import class_dc, spell_attack_bonus, die_average
from pf2e.spells import SPELL_REGISTRY, SpellPattern
from pf2e.types import DamageType, SaveType
from sim.party import make_dalai, make_aetregan, make_rook, make_erisen

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# SpellDefinition validation
# ---------------------------------------------------------------------------

class TestSpellDefinitions:

    def test_fear_fields(self):
        f = SPELL_REGISTRY["fear"]
        assert f.name == "Fear"
        assert f.action_cost == 2
        assert f.rank == 1
        assert f.pattern == SpellPattern.SAVE_OR_CONDITION
        assert f.save_type == SaveType.WILL
        assert f.is_basic_save is False
        assert f.range_ft == 30
        assert f.uses_spell_slot is True

    def test_force_barrage_fields(self):
        fb = SPELL_REGISTRY["force-barrage"]
        assert fb.name == "Force Barrage"
        assert fb.action_cost == 1
        assert fb.rank == 1
        assert fb.pattern == SpellPattern.AUTO_HIT_DAMAGE
        assert fb.range_ft == 120
        assert fb.damage_dice == 1
        assert fb.damage_die == "d4"
        assert fb.damage_bonus == 1
        assert fb.damage_type == DamageType.FORCE
        assert fb.scales_with_actions is True
        assert fb.missiles_per_action == 1

    def test_needle_darts_fields(self):
        nd = SPELL_REGISTRY["needle-darts"]
        assert nd.name == "Needle Darts"
        assert nd.action_cost == 2
        assert nd.rank == 0  # cantrip
        assert nd.pattern == SpellPattern.ATTACK_ROLL
        assert nd.range_ft == 60
        assert nd.damage_dice == 3
        assert nd.damage_die == "d4"
        assert nd.damage_type == DamageType.PIERCING
        assert nd.uses_spell_slot is False  # cantrip
        assert "attack" in nd.traits

    def test_all_dalai_combat_spells_in_registry(self):
        for slug in ["fear", "force-barrage", "needle-darts"]:
            assert slug in SPELL_REGISTRY


# ---------------------------------------------------------------------------
# DamageType.FORCE
# ---------------------------------------------------------------------------

class TestDamageTypeForce:
    def test_force_exists(self):
        assert DamageType.FORCE is not None
        assert DamageType.FORCE.name == "FORCE"


# ---------------------------------------------------------------------------
# spell_attack_bonus
# ---------------------------------------------------------------------------

class TestSpellAttackBonus:

    def test_dalai_spell_attack_bonus(self):
        """Dalai CHA +4 + trained(2) + level(1) = +7."""
        dalai = make_dalai()
        assert spell_attack_bonus(dalai) == 7

    def test_identity_with_class_dc(self):
        """spell_attack_bonus == class_dc - 10 for all characters."""
        for make_fn in [make_aetregan, make_rook, make_dalai, make_erisen]:
            c = make_fn()
            assert spell_attack_bonus(c) == class_dc(c) - 10


# ---------------------------------------------------------------------------
# Known spells on Character
# ---------------------------------------------------------------------------

class TestKnownSpells:

    def test_dalai_has_combat_spells(self):
        dalai = make_dalai()
        assert "needle-darts" in dalai.known_spells
        assert "fear" in dalai.known_spells
        assert "force-barrage" in dalai.known_spells

    def test_dalai_needle_darts_is_cantrip(self):
        dalai = make_dalai()
        assert dalai.known_spells["needle-darts"] == 0

    def test_dalai_fear_is_rank_1(self):
        dalai = make_dalai()
        assert dalai.known_spells["fear"] == 1

    def test_non_casters_empty(self):
        for make_fn in [make_aetregan, make_rook, make_erisen]:
            c = make_fn()
            assert c.known_spells == {}


# ---------------------------------------------------------------------------
# Force Barrage (auto-hit)
# ---------------------------------------------------------------------------

class TestForceBarrage:

    @pytest.fixture
    def state(self):
        from sim.scenario import load_scenario
        from sim.round_state import RoundState
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        return RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Aetregan", "Rook", "Erisen", "Bandit1"],
        )

    def test_1_action_damage(self, state):
        """1 missile: 1d4+1 = 3.5 avg."""
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=1, target_name="Bandit1", tactic_name="force-barrage",
        )
        result = evaluate_spell(action, state)
        assert result.eligible
        assert len(result.outcomes) == 1
        assert result.outcomes[0].probability == 1.0
        assert result.expected_damage_dealt == pytest.approx(3.5, abs=EV_TOLERANCE)

    def test_2_action_damage(self, state):
        """2 missiles: 2 × 3.5 = 7.0."""
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="force-barrage",
        )
        result = evaluate_spell(action, state)
        assert result.expected_damage_dealt == pytest.approx(7.0, abs=EV_TOLERANCE)

    def test_3_action_damage(self, state):
        """3 missiles: 3 × 3.5 = 10.5."""
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=3, target_name="Bandit1", tactic_name="force-barrage",
        )
        result = evaluate_spell(action, state)
        assert result.expected_damage_dealt == pytest.approx(10.5, abs=EV_TOLERANCE)

    def test_auto_hit_probability_1(self, state):
        """Force Barrage always hits — probability = 1.0."""
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=1, target_name="Bandit1", tactic_name="force-barrage",
        )
        result = evaluate_spell(action, state)
        assert result.outcomes[0].probability == 1.0


# ---------------------------------------------------------------------------
# Fear (condition spell)
# ---------------------------------------------------------------------------

class TestFear:

    @pytest.fixture
    def state(self):
        from sim.scenario import load_scenario
        from sim.round_state import RoundState
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        return RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Aetregan", "Rook", "Erisen", "Bandit1"],
        )

    def test_eligible_when_known(self, state):
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="fear",
        )
        result = evaluate_spell(action, state)
        assert result.eligible

    def test_ineligible_when_not_known(self, state):
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Rook",
            action_cost=2, target_name="Bandit1", tactic_name="fear",
        )
        result = evaluate_spell(action, state)
        assert not result.eligible

    def test_outcome_probabilities_sum_to_1(self, state):
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="fear",
        )
        result = evaluate_spell(action, state)
        total_prob = sum(o.probability for o in result.outcomes)
        assert total_prob == pytest.approx(1.0, abs=0.001)

    def test_has_multiple_outcomes(self, state):
        """Fear produces outcomes for each degree of success."""
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="fear",
        )
        result = evaluate_spell(action, state)
        assert len(result.outcomes) >= 3  # crit_success, success, failure, crit_failure


# ---------------------------------------------------------------------------
# Needle Darts (attack roll)
# ---------------------------------------------------------------------------

class TestNeedleDarts:

    @pytest.fixture
    def state(self):
        from sim.scenario import load_scenario
        from sim.round_state import RoundState
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        return RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Aetregan", "Rook", "Erisen", "Bandit1"],
        )

    def test_attack_roll_pattern(self, state):
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="needle-darts",
        )
        result = evaluate_spell(action, state)
        assert result.eligible
        # Should have miss/hit/crit outcomes
        assert len(result.outcomes) >= 2

    def test_base_damage(self, state):
        """3d4 avg = 7.5."""
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="needle-darts",
        )
        result = evaluate_spell(action, state)
        # Find the hit outcome
        hit_outcomes = [o for o in result.outcomes if "hit" in o.description and "crit" not in o.description]
        if hit_outcomes:
            assert hit_outcomes[0].hp_changes["Bandit1"] == pytest.approx(-7.5, abs=EV_TOLERANCE)

    def test_crit_double_damage(self, state):
        """Crit = 2 × 7.5 = 15.0."""
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="needle-darts",
        )
        result = evaluate_spell(action, state)
        crit_outcomes = [o for o in result.outcomes if "crit" in o.description]
        if crit_outcomes:
            assert crit_outcomes[0].hp_changes["Bandit1"] == pytest.approx(-15.0, abs=EV_TOLERANCE)

    def test_cantrip_unlimited(self):
        nd = SPELL_REGISTRY["needle-darts"]
        assert nd.uses_spell_slot is False

    def test_probabilities_sum_to_1(self, state):
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="needle-darts",
        )
        result = evaluate_spell(action, state)
        total = sum(o.probability for o in result.outcomes)
        assert total == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

class TestSpellInfrastructure:

    def test_unknown_slug_ineligible(self):
        from sim.scenario import load_scenario
        from sim.round_state import RoundState
        scenario = load_scenario("scenarios/checkpoint_1_strike_hard.scenario")
        state = RoundState.from_scenario(
            scenario, ["Dalai Alpaca", "Aetregan", "Rook", "Erisen", "Bandit1"],
        )
        action = Action(
            type=ActionType.CAST_SPELL, actor_name="Dalai Alpaca",
            action_cost=2, target_name="Bandit1", tactic_name="nonexistent-spell",
        )
        result = evaluate_spell(action, state)
        assert not result.eligible

    def test_cast_spell_in_dispatcher(self):
        from pf2e.actions import _ACTION_EVALUATORS
        assert ActionType.CAST_SPELL in _ACTION_EVALUATORS
