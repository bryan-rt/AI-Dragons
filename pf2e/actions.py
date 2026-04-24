"""Action types and data structures for the turn evaluator.

Actions are the atomic choices a character makes during combat. Each
ActionType has an associated evaluator (implemented in Pass 3c) that
computes the outcome distribution for a given (action, state) pair.

Pass 3a delivers only the types — evaluators come in 3c.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class ActionType(Enum):
    """All action types enumerable in CP5.1.

    Taxonomy:
    - Movement: STRIDE, STEP
    - Combat: STRIKE, TRIP, DISARM
    - Defense: RAISE_SHIELD, SHIELD_BLOCK (reaction)
    - Commander: PLANT_BANNER, ACTIVATE_TACTIC
    - Skill actions: DEMORALIZE, CREATE_A_DIVERSION, FEINT
    - Guardian reactions: INTERCEPT_ATTACK, EVER_READY
    - Control: END_TURN

    CP5.2 will add Taunt, healing, compositions, spells.
    CP5.3 will add Aid, Recall Knowledge, Seek/Hide/Sneak.
    """
    STRIDE = auto()
    STEP = auto()
    STRIKE = auto()
    TRIP = auto()
    DISARM = auto()
    RAISE_SHIELD = auto()
    SHIELD_BLOCK = auto()
    PLANT_BANNER = auto()
    ACTIVATE_TACTIC = auto()
    DEMORALIZE = auto()
    CREATE_A_DIVERSION = auto()
    FEINT = auto()
    INTERCEPT_ATTACK = auto()
    EVER_READY = auto()
    END_TURN = auto()


@dataclass(frozen=True)
class Action:
    """A specific instance of an action, fully parameterized.

    Example:
        Action(type=ActionType.STRIDE, actor_name="Rook",
               action_cost=1, target_position=(5, 8))
        Action(type=ActionType.STRIKE, actor_name="Aetregan",
               action_cost=1, target_name="Bandit1",
               weapon_name="Scorpion Whip")
        Action(type=ActionType.ACTIVATE_TACTIC, actor_name="Aetregan",
               action_cost=2, tactic_name="Strike Hard!")

    Unused fields stay at their defaults (empty string or None).
    The evaluator for each ActionType knows which fields are meaningful.
    """
    type: ActionType
    actor_name: str
    action_cost: int
    target_name: str = ""
    target_position: tuple[int, int] | None = None
    target_names: tuple[str, ...] = ()
    weapon_name: str = ""
    tactic_name: str = ""


@dataclass(frozen=True)
class ActionOutcome:
    """One branch of an action's probability tree.

    Each outcome is a complete state-delta specification: what HP changes,
    what positions move, what conditions are applied or removed.

    All dicts are convention-immutable after construction.
    """
    probability: float
    hp_changes: dict[str, float] = field(default_factory=dict)
    position_changes: dict[str, tuple[int, int]] = field(default_factory=dict)
    conditions_applied: dict[str, tuple[str, ...]] = field(default_factory=dict)
    conditions_removed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reactions_consumed: dict[str, int] = field(default_factory=dict)
    description: str = ""


@dataclass(frozen=True)
class ActionResult:
    """The evaluator's output for a single (action, state) pair.

    If eligible is False, outcomes is empty and ineligibility_reason explains.
    If eligible is True, outcomes probabilities sum to ~1.0.
    """
    action: Action
    outcomes: tuple[ActionOutcome, ...] = ()
    eligible: bool = True
    ineligibility_reason: str = ""

    @property
    def expected_damage_dealt(self) -> float:
        """Expected damage TO enemies across all outcomes.

        Negative hp_changes values represent damage dealt.
        """
        total = 0.0
        for outcome in self.outcomes:
            for delta in outcome.hp_changes.values():
                if delta < 0:
                    total += outcome.probability * (-delta)
        return total

    def verify_probability_sum(self, tolerance: float = 1e-6) -> bool:
        """Sanity check: outcome probabilities sum to ~1.0 for eligible actions."""
        if not self.eligible:
            return len(self.outcomes) == 0
        total = sum(o.probability for o in self.outcomes)
        return abs(total - 1.0) < tolerance
