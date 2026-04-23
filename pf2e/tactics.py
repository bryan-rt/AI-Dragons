"""Commander tactic definitions, dispatcher, and evaluators.

The five folio tactics for Aetregan (Battlecry! Commander, level 1):
- Strike Hard! (offensive, 2 actions)
- Gather to Me! (mobility, 1 action)
- Tactical Takedown (offensive, 2 actions)
- Defensive Retreat (mobility, 2 actions — placeholder evaluator)
- Mountaineering Training (mobility, 1 action — placeholder evaluator)

Three are prepared by default; the other two are in the folio for future
re-preparation.

(AoN: https://2e.aonprd.com/Tactics.aspx)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from pf2e.character import CombatantState, EnemyState  # EnemyState re-exported
from pf2e.combat_math import (
    attack_bonus,
    class_dc,
    effective_speed,
    enumerate_d20_outcomes,
    expected_strike_damage,
)
from pf2e.equipment import EquippedWeapon
from pf2e.types import SaveType


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TacticDefinition:
    """Declarative description of a Commander tactic.

    Each tactic in the Commander's folio is a frozen instance. Evaluator
    functions read these fields to determine eligibility, compute EV,
    and generate justification text.

    (AoN: https://2e.aonprd.com/Tactics.aspx)
    """
    name: str
    aon_url: str
    action_cost: int
    traits: frozenset[str]
    range_type: str          # "banner_aura" or "signal_all"
    target_type: str         # "one_squadmate", "two_squadmates", etc.
    granted_action: str      # key into _EVALUATORS dispatch table
    modifiers: dict[str, Any]
    prerequisites: tuple[str, ...]


class SpatialQueries(Protocol):
    """Abstract spatial query interface.

    Checkpoint 1: MockSpatialQueries with pre-computed data.
    Checkpoint 2: GridSpatialQueries backed by a real grid.
    """

    def is_in_banner_aura(self, combatant_name: str) -> bool: ...

    def enemies_reachable_by(self, combatant_name: str) -> list[str]: ...

    def is_adjacent(self, a_name: str, b_name: str) -> bool: ...

    def can_reach_with_stride(
        self, combatant_name: str, target_name: str, max_distance_ft: int,
    ) -> bool: ...

    def distance_ft(self, a_name: str, b_name: str) -> int: ...


@dataclass
class MockSpatialQueries:
    """Test double for SpatialQueries. All answers pre-computed."""

    in_aura: dict[str, bool] = field(default_factory=dict)
    reachable_enemies: dict[str, list[str]] = field(default_factory=dict)
    adjacencies: set[tuple[str, str]] = field(default_factory=set)
    distances: dict[tuple[str, str], int] = field(default_factory=dict)

    def is_in_banner_aura(self, name: str) -> bool:
        return self.in_aura.get(name, False)

    def enemies_reachable_by(self, name: str) -> list[str]:
        return self.reachable_enemies.get(name, [])

    def is_adjacent(self, a: str, b: str) -> bool:
        return (a, b) in self.adjacencies or (b, a) in self.adjacencies

    def can_reach_with_stride(
        self, name: str, target: str, max_ft: int,
    ) -> bool:
        dist = self.distances.get(
            (name, target),
            self.distances.get((target, name), 999),
        )
        return dist <= max_ft

    def distance_ft(self, a: str, b: str) -> int:
        return self.distances.get(
            (a, b), self.distances.get((b, a), 999),
        )


@dataclass
class TacticContext:
    """Everything a tactic evaluator needs."""

    commander: CombatantState
    squadmates: list[CombatantState]
    enemies: list[EnemyState]
    banner_position: tuple[int, int] | None
    banner_planted: bool
    spatial: SpatialQueries
    anthem_active: bool = True

    def get_squadmate(self, name: str) -> CombatantState | None:
        """Look up a squadmate's CombatantState by name."""
        for sq in self.squadmates:
            if sq.character.name == name:
                return sq
        return None

    def get_enemy(self, name: str) -> EnemyState | None:
        """Look up an enemy by name."""
        for e in self.enemies:
            if e.name == name:
                return e
        return None


@dataclass(frozen=True)
class TacticResult:
    """The evaluated outcome of considering a single tactic."""

    tactic_name: str
    action_cost: int
    eligible: bool
    ineligibility_reason: str = ""

    # EV components
    expected_damage_dealt: float = 0.0
    expected_damage_avoided: float = 0.0  # Checkpoint 4 populates

    # Best target selection
    best_target_ally: str = ""
    best_target_enemy: str = ""
    justification: str = ""

    # Conditions applied to enemies by this tactic.
    # e.g., {"Bandit1": ["prone"]}
    conditions_applied: dict[str, list[str]] = field(default_factory=dict)

    # Probability each condition is applied.
    # e.g., {"Bandit1": {"prone": 0.55}}
    condition_probabilities: dict[str, dict[str, float]] = field(
        default_factory=dict,
    )

    # Count of squadmates who can actually respond
    squadmates_responding: int = 0

    @property
    def net_value(self) -> float:
        return self.expected_damage_dealt + self.expected_damage_avoided


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

STRIKE_HARD = TacticDefinition(
    name="Strike Hard!",
    aon_url="https://2e.aonprd.com/Tactics.aspx?ID=13",
    action_cost=2,
    traits=frozenset({"offensive", "brandish"}),
    range_type="banner_aura",
    target_type="one_squadmate",
    granted_action="reaction_strike",
    modifiers={},
    prerequisites=("squadmate_in_aura",),
)

GATHER_TO_ME = TacticDefinition(
    name="Gather to Me!",
    aon_url="https://2e.aonprd.com/Tactics.aspx?ID=2",
    action_cost=1,
    traits=frozenset({"mobility"}),
    range_type="signal_all",
    target_type="all_squadmates",
    granted_action="reaction_stride",
    modifiers={"must_end_in_aura": True},
    prerequisites=(),
)

TACTICAL_TAKEDOWN = TacticDefinition(
    name="Tactical Takedown",
    aon_url="https://2e.aonprd.com/Tactics.aspx?ID=14",
    action_cost=2,
    traits=frozenset({"offensive"}),
    range_type="banner_aura",
    target_type="two_squadmates",
    granted_action="stride_half_speed",
    modifiers={
        "prone_on_fail": True,
        "save_type": "reflex",
        "must_end_adjacent_to_enemy": True,
    },
    prerequisites=("two_squadmates_in_aura",),
)

DEFENSIVE_RETREAT = TacticDefinition(
    name="Defensive Retreat",
    aon_url="https://2e.aonprd.com/Tactics.aspx?ID=1",
    action_cost=2,
    traits=frozenset({"brandish", "mobility"}),
    range_type="banner_aura",
    target_type="all_squadmates_in_aura",
    granted_action="free_step",
    modifiers={
        "max_steps": 3,
        "must_move_away_from_enemy": True,
    },
    prerequisites=("squadmate_in_aura",),
)

MOUNTAINEERING_TRAINING = TacticDefinition(
    name="Mountaineering Training",
    aon_url="https://2e.aonprd.com/Tactics.aspx?ID=3",
    action_cost=1,
    traits=frozenset({"mobility"}),
    range_type="signal_all",
    target_type="all_squadmates",
    granted_action="passive_buff",
    modifiers={"climb_speed": 20, "warfare_lore_for_climb": True},
    prerequisites=(),
)

FOLIO_TACTICS: dict[str, TacticDefinition] = {
    "strike_hard": STRIKE_HARD,
    "gather_to_me": GATHER_TO_ME,
    "tactical_takedown": TACTICAL_TAKEDOWN,
    "defensive_retreat": DEFENSIVE_RETREAT,
    "mountaineering_training": MOUNTAINEERING_TRAINING,
}

PREPARED_TACTICS: tuple[str, ...] = (
    "strike_hard",
    "gather_to_me",
    "tactical_takedown",
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _has_reaction(sq: CombatantState) -> bool:
    """True if the squadmate can respond with a reaction."""
    return sq.reactions_available > 0 or sq.drilled_reaction_available


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------

def _evaluate_reaction_strike(
    defn: TacticDefinition,
    ctx: TacticContext,
) -> TacticResult:
    """Strike Hard! — ally makes a reaction Strike at MAP 0.

    Signal a squadmate in banner aura; they immediately attempt a
    Strike as a reaction. Reaction Strikes are always MAP 0.

    (AoN: https://2e.aonprd.com/Tactics.aspx?ID=13)
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=220 — MAP doesn't apply to reactions)
    """
    best_ev = -1.0
    best_ally = ""
    best_enemy = ""
    best_weapon_name = ""
    best_bonus = 0

    for sq in ctx.squadmates:
        name = sq.character.name
        if not ctx.spatial.is_in_banner_aura(name):
            continue
        if not _has_reaction(sq):
            continue
        reachable = ctx.spatial.enemies_reachable_by(name)
        if not reachable:
            continue

        for enemy_name in reachable:
            enemy = ctx.get_enemy(enemy_name)
            if enemy is None:
                continue
            for equipped in sq.character.equipped_weapons:
                ev = expected_strike_damage(
                    sq, equipped, enemy.ac,
                    is_reaction=True,
                    off_guard=enemy.off_guard,
                )
                if ev > best_ev:
                    best_ev = ev
                    best_ally = name
                    best_enemy = enemy_name
                    best_weapon_name = equipped.weapon.name
                    best_bonus = attack_bonus(sq, equipped)

    if best_ev < 0:
        # No valid combination found
        # Determine why for the ineligibility reason
        any_in_aura = any(
            ctx.spatial.is_in_banner_aura(sq.character.name)
            for sq in ctx.squadmates
        )
        if not any_in_aura:
            reason = "No squadmates in banner aura."
        else:
            has_reactions = any(
                _has_reaction(sq)
                for sq in ctx.squadmates
                if ctx.spatial.is_in_banner_aura(sq.character.name)
            )
            if not has_reactions:
                reason = "No squadmates in aura have reactions available."
            else:
                reason = (
                    "No enemies in reach of any squadmate in aura."
                )
        return TacticResult(
            tactic_name=defn.name,
            action_cost=defn.action_cost,
            eligible=False,
            ineligibility_reason=reason,
        )

    return TacticResult(
        tactic_name=defn.name,
        action_cost=defn.action_cost,
        eligible=True,
        expected_damage_dealt=best_ev,
        best_target_ally=best_ally,
        best_target_enemy=best_enemy,
        justification=(
            f"Strike Hard! \u2192 {best_ally} {best_weapon_name} "
            f"reaction Strike at {best_bonus:+d} (MAP 0) vs "
            f"{best_enemy} AC {ctx.get_enemy(best_enemy).ac}, "  # type: ignore[union-attr]
            f"EV {best_ev:.2f}"
        ),
        squadmates_responding=1,
    )


def _evaluate_reaction_stride(
    defn: TacticDefinition,
    ctx: TacticContext,
) -> TacticResult:
    """Gather to Me! — all squadmates Stride toward banner aura.

    Always eligible. Value is purely defensive (Checkpoint 4).
    Tracks which squadmates can actually respond (have reactions).

    (AoN: https://2e.aonprd.com/Tactics.aspx?ID=2)
    """
    will_respond: list[str] = []
    cannot_respond: list[str] = []

    for sq in ctx.squadmates:
        name = sq.character.name
        if _has_reaction(sq):
            will_respond.append(name)
        else:
            cannot_respond.append(name)

    total = len(ctx.squadmates)
    responding = len(will_respond)

    no_react_note = ""
    if cannot_respond:
        names = ", ".join(cannot_respond)
        verb = "has" if len(cannot_respond) == 1 else "have"
        no_react_note = f"; {names} {verb} no reactions available"

    justification = (
        f"Gather to Me! \u2192 {responding} of {total} squadmates "
        f"Stride toward banner aura as reactions "
        f"({defn.action_cost} action){no_react_note}. "
        f"Defensive value pending Checkpoint 4."
    )

    return TacticResult(
        tactic_name=defn.name,
        action_cost=defn.action_cost,
        eligible=True,
        expected_damage_dealt=0.0,
        justification=justification,
        squadmates_responding=responding,
    )


def _evaluate_stride_half(
    defn: TacticDefinition,
    ctx: TacticContext,
) -> TacticResult:
    """Tactical Takedown — two allies half-Stride, enemy Reflex save or prone.

    Signal up to two squadmates in banner aura. Each Strides up to half
    their Speed as a reaction. If both end adjacent to an enemy, that
    enemy Reflex saves vs Commander class DC or falls prone.

    Crit fail = fail = prone (no enhanced crit fail effect).

    (AoN: https://2e.aonprd.com/Tactics.aspx?ID=14)
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=88 — Prone)
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2195 — basic saves)
    """
    # Find eligible squadmates (in aura + have reactions)
    eligible_allies: list[CombatantState] = []
    for sq in ctx.squadmates:
        if (ctx.spatial.is_in_banner_aura(sq.character.name)
                and _has_reaction(sq)):
            eligible_allies.append(sq)

    if len(eligible_allies) < 2:
        return TacticResult(
            tactic_name=defn.name,
            action_cost=defn.action_cost,
            eligible=False,
            ineligibility_reason=(
                "Fewer than 2 squadmates in banner aura with reactions."
            ),
        )

    # Find valid (pair, enemy) combinations where both can reach with half-Speed
    dc = class_dc(ctx.commander.character)
    best_prone_prob = -1.0
    best_pair: tuple[str, str] = ("", "")
    best_enemy_name = ""
    best_save_mod = 0

    for i, ally1 in enumerate(eligible_allies):
        for ally2 in eligible_allies[i + 1:]:
            half1 = effective_speed(ally1) // 2
            half2 = effective_speed(ally2) // 2
            for enemy in ctx.enemies:
                can1 = ctx.spatial.can_reach_with_stride(
                    ally1.character.name, enemy.name, half1,
                )
                can2 = ctx.spatial.can_reach_with_stride(
                    ally2.character.name, enemy.name, half2,
                )
                if can1 and can2:
                    save_mod = enemy.saves[SaveType.REFLEX]
                    outcomes = enumerate_d20_outcomes(save_mod, dc)
                    prone_prob = (
                        outcomes.failure + outcomes.critical_failure
                    ) / 20
                    if prone_prob > best_prone_prob:
                        best_prone_prob = prone_prob
                        best_pair = (
                            ally1.character.name,
                            ally2.character.name,
                        )
                        best_enemy_name = enemy.name
                        best_save_mod = save_mod

    if best_prone_prob < 0:
        return TacticResult(
            tactic_name=defn.name,
            action_cost=defn.action_cost,
            eligible=False,
            ineligibility_reason=(
                "No enemy reachable by 2 squadmates with half-Speed Stride."
            ),
        )

    return TacticResult(
        tactic_name=defn.name,
        action_cost=defn.action_cost,
        eligible=True,
        expected_damage_dealt=0.0,
        best_target_ally=f"{best_pair[0]} + {best_pair[1]}",
        best_target_enemy=best_enemy_name,
        justification=(
            f"Tactical Takedown \u2192 {best_pair[0]} + {best_pair[1]} "
            f"Stride to flank {best_enemy_name}. "
            f"{best_enemy_name} Reflex {best_save_mod:+d} vs DC {dc}: "
            f"{best_prone_prob:.0%} chance prone."
        ),
        conditions_applied={best_enemy_name: ["prone"]},
        condition_probabilities={
            best_enemy_name: {"prone": best_prone_prob},
        },
        squadmates_responding=2,
    )


def _evaluate_free_step(
    defn: TacticDefinition,
    ctx: TacticContext,
) -> TacticResult:
    """Defensive Retreat — placeholder evaluator.

    Allies Step up to 3 times as free actions (not reactions) away
    from enemies. Full evaluation requires spatial reasoning
    (Checkpoint 2) and defensive value computation (Checkpoint 4).

    (AoN: https://2e.aonprd.com/Tactics.aspx?ID=1)
    """
    any_in_aura = any(
        ctx.spatial.is_in_banner_aura(sq.character.name)
        for sq in ctx.squadmates
    )
    if not any_in_aura:
        return TacticResult(
            tactic_name=defn.name,
            action_cost=defn.action_cost,
            eligible=False,
            ineligibility_reason="No squadmates in banner aura.",
        )

    return TacticResult(
        tactic_name=defn.name,
        action_cost=defn.action_cost,
        eligible=True,
        expected_damage_dealt=0.0,
        justification=(
            f"Defensive Retreat \u2192 Squadmates Step away from enemies "
            f"({defn.action_cost} actions). "
            f"Defensive value pending Checkpoint 4."
        ),
    )


def _evaluate_passive_buff(
    defn: TacticDefinition,
    ctx: TacticContext,
) -> TacticResult:
    """Mountaineering Training — placeholder evaluator.

    Grants climb Speed 20 ft. Situational value only.

    (AoN: https://2e.aonprd.com/Tactics.aspx?ID=3)
    """
    return TacticResult(
        tactic_name=defn.name,
        action_cost=defn.action_cost,
        eligible=True,
        expected_damage_dealt=0.0,
        justification=(
            f"Mountaineering Training \u2192 Passive buff "
            f"({defn.action_cost} action). "
            f"No vertical terrain in scenario; situational value not computed."
        ),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_EVALUATORS: dict[
    str, Callable[[TacticDefinition, TacticContext], TacticResult]
] = {
    "reaction_strike": _evaluate_reaction_strike,
    "reaction_stride": _evaluate_reaction_stride,
    "stride_half_speed": _evaluate_stride_half,
    "free_step": _evaluate_free_step,
    "passive_buff": _evaluate_passive_buff,
}


def evaluate_tactic(
    definition: TacticDefinition,
    context: TacticContext,
) -> TacticResult:
    """Evaluate a single tactic. Routes by granted_action.

    (AoN: https://2e.aonprd.com/Tactics.aspx)
    """
    evaluator = _EVALUATORS.get(definition.granted_action)
    if evaluator is None:
        return TacticResult(
            tactic_name=definition.name,
            action_cost=definition.action_cost,
            eligible=False,
            ineligibility_reason=(
                f"No evaluator for granted_action="
                f"{definition.granted_action!r}"
            ),
        )
    return evaluator(definition, context)


def evaluate_all_prepared(
    prepared: list[TacticDefinition],
    context: TacticContext,
) -> list[TacticResult]:
    """Evaluate all prepared tactics, return sorted by net_value descending."""
    results = [evaluate_tactic(t, context) for t in prepared]
    return sorted(results, key=lambda r: r.net_value, reverse=True)
