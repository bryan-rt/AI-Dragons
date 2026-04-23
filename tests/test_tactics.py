"""Tests for tactic representation and dispatcher.

Validates eligibility checks, EV computations, and justification text
for all 5 folio tactics. Spatial queries are mocked via MockSpatialQueries.
"""

import pytest

from pf2e.character import CombatantState
from pf2e.combat_math import expected_strike_damage
from pf2e.equipment import EquippedWeapon
from pf2e.tactics import (
    DEFENSIVE_RETREAT,
    GATHER_TO_ME,
    MOUNTAINEERING_TRAINING,
    STRIKE_HARD,
    TACTICAL_TAKEDOWN,
    EnemyState,
    MockSpatialQueries,
    TacticContext,
    evaluate_all_prepared,
    evaluate_tactic,
)
from pf2e.types import SaveType
from tests.fixtures import (
    LONGSWORD,
    RAPIER,
    make_aetregan,
    make_dalai,
    make_erisen,
    make_rook,
    make_rook_combat_state,
)

EV_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bandit1() -> EnemyState:
    return EnemyState(
        name="Bandit1",
        ac=15,
        saves={SaveType.REFLEX: 5, SaveType.FORTITUDE: 3, SaveType.WILL: 2},
        position=(3, 5),
    )


@pytest.fixture
def base_context(bandit1: EnemyState) -> TacticContext:
    """Default context: all four party members, one bandit, anthem active."""
    aetregan = CombatantState.from_character(make_aetregan(), anthem_active=True)
    rook = make_rook_combat_state(anthem_active=True)
    dalai = CombatantState.from_character(make_dalai(), anthem_active=True)
    erisen = CombatantState.from_character(make_erisen(), anthem_active=True)
    return TacticContext(
        commander=aetregan,
        squadmates=[rook, dalai, erisen],
        enemies=[bandit1],
        banner_position=(3, 3),
        banner_planted=True,
        spatial=MockSpatialQueries(),
        anthem_active=True,
    )


# ---------------------------------------------------------------------------
# Strike Hard! tests
# ---------------------------------------------------------------------------

class TestStrikeHard:

    def test_eligible_rook_strikes_bandit(
        self, base_context: TacticContext,
    ) -> None:
        """Rook in aura + Bandit in reach → reaction Strike at MAP 0.

        With Anthem active: Rook longsword +8 vs AC 15, damage 9.5 avg.
        d20: crit fail 1, fail 5, hit 10, crit 4. EV = 8.55.
        """
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True, "Erisen": False},
            reachable_enemies={"Rook": ["Bandit1"], "Dalai Alpaca": []},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert result.eligible
        assert result.best_target_ally == "Rook"
        assert result.best_target_enemy == "Bandit1"
        assert result.expected_damage_dealt == pytest.approx(8.55, abs=EV_TOLERANCE)
        assert result.squadmates_responding == 1
        assert "MAP 0" in result.justification

    def test_ineligible_no_squadmate_in_aura(
        self, base_context: TacticContext,
    ) -> None:
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": False, "Dalai Alpaca": False, "Erisen": False},
            reachable_enemies={"Rook": ["Bandit1"]},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert not result.eligible
        assert "aura" in result.ineligibility_reason.lower()

    def test_ineligible_no_reachable_enemy(
        self, base_context: TacticContext,
    ) -> None:
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True},
            reachable_enemies={"Rook": []},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert not result.eligible
        assert "reach" in result.ineligibility_reason.lower()

    def test_picks_best_ally(self, base_context: TacticContext) -> None:
        """Both Rook and Dalai in aura + reachable enemy. Rook wins on EV."""
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            reachable_enemies={
                "Rook": ["Bandit1"],
                "Dalai Alpaca": ["Bandit1"],
            },
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert result.eligible
        assert result.best_target_ally == "Rook"

    def test_skips_ally_without_reactions(
        self, base_context: TacticContext,
    ) -> None:
        """Rook has no reactions; Dalai responds instead."""
        base_context.squadmates[0].reactions_available = 0
        base_context.squadmates[0].drilled_reaction_available = False
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            reachable_enemies={
                "Rook": ["Bandit1"],
                "Dalai Alpaca": ["Bandit1"],
            },
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert result.eligible
        assert result.best_target_ally == "Dalai Alpaca"

    def test_drilled_reaction_allows_depleted_ally(
        self, base_context: TacticContext,
    ) -> None:
        """Rook has 0 reactions but drilled_reaction_available=True."""
        base_context.squadmates[0].reactions_available = 0
        base_context.squadmates[0].drilled_reaction_available = True
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True},
            reachable_enemies={"Rook": ["Bandit1"]},
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert result.eligible
        assert result.best_target_ally == "Rook"

    def test_ineligible_all_in_aura_no_reactions(
        self, base_context: TacticContext,
    ) -> None:
        """All squadmates in aura but none have reactions."""
        for sq in base_context.squadmates:
            sq.reactions_available = 0
            sq.drilled_reaction_available = False
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True, "Erisen": True},
            reachable_enemies={
                "Rook": ["Bandit1"],
                "Dalai Alpaca": ["Bandit1"],
                "Erisen": ["Bandit1"],
            },
        )
        result = evaluate_tactic(STRIKE_HARD, base_context)
        assert not result.eligible
        assert "reaction" in result.ineligibility_reason.lower()

    def test_off_guard_enemy_increases_ev(
        self, base_context: TacticContext, bandit1: EnemyState,
    ) -> None:
        """Off-guard enemy → -2 effective AC → higher EV."""
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True},
            reachable_enemies={"Rook": ["Bandit1"]},
        )
        result_normal = evaluate_tactic(STRIKE_HARD, base_context)

        bandit1.off_guard = True
        result_offguard = evaluate_tactic(STRIKE_HARD, base_context)

        assert result_offguard.expected_damage_dealt > result_normal.expected_damage_dealt


# ---------------------------------------------------------------------------
# Gather to Me! tests
# ---------------------------------------------------------------------------

class TestGatherToMe:

    def test_always_eligible(self, base_context: TacticContext) -> None:
        base_context.spatial = MockSpatialQueries()
        result = evaluate_tactic(GATHER_TO_ME, base_context)
        assert result.eligible
        assert result.expected_damage_dealt == 0.0
        assert "pending" in result.justification.lower()

    def test_response_count_all(self, base_context: TacticContext) -> None:
        """All 3 squadmates have reactions → 3 of 3."""
        result = evaluate_tactic(GATHER_TO_ME, base_context)
        assert result.squadmates_responding == 3
        assert "3 of 3" in result.justification

    def test_partial_response(self, base_context: TacticContext) -> None:
        """Erisen used his reaction → 2 of 3 can respond."""
        base_context.squadmates[2].reactions_available = 0
        result = evaluate_tactic(GATHER_TO_ME, base_context)
        assert result.squadmates_responding == 2
        assert "2 of 3" in result.justification
        assert "Erisen" in result.justification

    def test_zero_responders(self, base_context: TacticContext) -> None:
        """All squadmates out of reactions → still eligible but 0 respond."""
        for sq in base_context.squadmates:
            sq.reactions_available = 0
        result = evaluate_tactic(GATHER_TO_ME, base_context)
        assert result.eligible
        assert result.squadmates_responding == 0
        assert "0 of 3" in result.justification


# ---------------------------------------------------------------------------
# Tactical Takedown tests
# ---------------------------------------------------------------------------

class TestTacticalTakedown:

    def test_eligible_two_allies_reach_enemy(
        self, base_context: TacticContext,
    ) -> None:
        """Rook (speed 20, half=10) and Dalai (speed 25, half=12) both reach.

        Bandit1 Reflex +5 vs DC 17: 55% prone.
        """
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True, "Erisen": False},
            distances={
                ("Rook", "Bandit1"): 10,
                ("Dalai Alpaca", "Bandit1"): 10,
            },
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, base_context)
        assert result.eligible
        assert result.expected_damage_dealt == 0.0
        assert result.conditions_applied == {"Bandit1": ["prone"]}
        assert result.condition_probabilities["Bandit1"]["prone"] == pytest.approx(
            0.55, abs=0.01,
        )
        assert result.squadmates_responding == 2
        assert "55%" in result.justification

    def test_ineligible_one_ally_in_aura(
        self, base_context: TacticContext,
    ) -> None:
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": False, "Erisen": False},
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, base_context)
        assert not result.eligible
        assert "2" in result.ineligibility_reason

    def test_ineligible_no_shared_reachable_enemy(
        self, base_context: TacticContext,
    ) -> None:
        """Both in aura but enemy too far for half-Speed Stride."""
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            distances={
                ("Rook", "Bandit1"): 50,
                ("Dalai Alpaca", "Bandit1"): 50,
            },
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, base_context)
        assert not result.eligible
        assert "reachable" in result.ineligibility_reason.lower()

    def test_one_ally_too_slow(self, base_context: TacticContext) -> None:
        """Rook can reach (10 ≤ 10) but Dalai can't (15 > 12)."""
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True, "Erisen": True},
            distances={
                ("Rook", "Bandit1"): 10,
                ("Dalai Alpaca", "Bandit1"): 15,
                ("Erisen", "Bandit1"): 15,
            },
        )
        # Rook half=10, Dalai half=12, Erisen half=17
        # Rook+Dalai: Rook 10≤10 ✓, Dalai 15>12 ✗
        # Rook+Erisen: Rook 10≤10 ✓, Erisen 15≤17 ✓ → valid pair!
        result = evaluate_tactic(TACTICAL_TAKEDOWN, base_context)
        assert result.eligible
        assert "Rook" in result.best_target_ally
        assert "Erisen" in result.best_target_ally

    def test_picks_lowest_save_enemy(
        self, base_context: TacticContext,
    ) -> None:
        """With 2 enemies, picks the one more likely to fall prone."""
        weak_bandit = EnemyState(
            name="WeakBandit",
            ac=13,
            saves={SaveType.REFLEX: 2, SaveType.FORTITUDE: 1, SaveType.WILL: 0},
            position=(3, 6),
        )
        base_context.enemies.append(weak_bandit)
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            distances={
                ("Rook", "Bandit1"): 10,
                ("Dalai Alpaca", "Bandit1"): 10,
                ("Rook", "WeakBandit"): 10,
                ("Dalai Alpaca", "WeakBandit"): 10,
            },
        )
        result = evaluate_tactic(TACTICAL_TAKEDOWN, base_context)
        assert result.eligible
        # WeakBandit Reflex +2 vs DC 17 → more prone prob than Bandit1 +5
        assert result.best_target_enemy == "WeakBandit"


# ---------------------------------------------------------------------------
# Defensive Retreat tests
# ---------------------------------------------------------------------------

class TestDefensiveRetreat:

    def test_eligible_squadmate_in_aura(
        self, base_context: TacticContext,
    ) -> None:
        base_context.spatial = MockSpatialQueries(in_aura={"Rook": True})
        result = evaluate_tactic(DEFENSIVE_RETREAT, base_context)
        assert result.eligible
        assert result.expected_damage_dealt == 0.0
        assert "pending" in result.justification.lower()

    def test_ineligible_no_squadmate_in_aura(
        self, base_context: TacticContext,
    ) -> None:
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": False, "Dalai Alpaca": False, "Erisen": False},
        )
        result = evaluate_tactic(DEFENSIVE_RETREAT, base_context)
        assert not result.eligible
        assert "aura" in result.ineligibility_reason.lower()


# ---------------------------------------------------------------------------
# Mountaineering Training tests
# ---------------------------------------------------------------------------

class TestMountaineeringTraining:

    def test_always_eligible_zero_ev(
        self, base_context: TacticContext,
    ) -> None:
        result = evaluate_tactic(MOUNTAINEERING_TRAINING, base_context)
        assert result.eligible
        assert result.expected_damage_dealt == 0.0
        assert "situational" in result.justification.lower()


# ---------------------------------------------------------------------------
# evaluate_all_prepared tests
# ---------------------------------------------------------------------------

class TestEvaluateAllPrepared:

    def test_sorts_by_net_value(self, base_context: TacticContext) -> None:
        """Strike Hard should rank first (has damage EV)."""
        base_context.spatial = MockSpatialQueries(
            in_aura={"Rook": True, "Dalai Alpaca": True},
            reachable_enemies={"Rook": ["Bandit1"]},
            distances={
                ("Rook", "Bandit1"): 10,
                ("Dalai Alpaca", "Bandit1"): 10,
            },
        )
        prepared = [STRIKE_HARD, GATHER_TO_ME, TACTICAL_TAKEDOWN]
        results = evaluate_all_prepared(prepared, base_context)
        assert len(results) == 3
        assert results[0].tactic_name == "Strike Hard!"
        assert results[0].net_value > 0
        # Gather to Me and Tactical Takedown both have 0 damage EV
        assert results[1].net_value == 0.0
        assert results[2].net_value == 0.0

    def test_returns_all_results_even_if_ineligible(
        self, base_context: TacticContext,
    ) -> None:
        """Even ineligible tactics appear in results."""
        base_context.spatial = MockSpatialQueries()  # nothing in aura
        prepared = [STRIKE_HARD, GATHER_TO_ME, TACTICAL_TAKEDOWN]
        results = evaluate_all_prepared(prepared, base_context)
        assert len(results) == 3
        # Gather to Me is always eligible; the others aren't
        eligible_names = {r.tactic_name for r in results if r.eligible}
        assert "Gather to Me!" in eligible_names
