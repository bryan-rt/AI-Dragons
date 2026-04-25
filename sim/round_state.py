"""Frozen combat state for search-tree branching.

CombatantSnapshot and EnemySnapshot are immutable projections of their
mutable counterparts. RoundState holds dicts of snapshots and provides
with_pc_update / with_enemy_update for cheap branching.

The underlying Character objects are shared across all branches.
GridState is shared (effectively immutable post-construction).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from pf2e.character import Character, CombatantState, EnemyState
from pf2e.combat_math import max_hp
from pf2e.types import SaveType

if TYPE_CHECKING:
    from sim.grid import GridState
    from sim.scenario import Scenario


@dataclass(frozen=True)
class CombatantSnapshot:
    """Immutable projection of a CombatantState for search branching.

    Branching creates new instances via dataclasses.replace(). The
    underlying Character is shared across all branches.
    """
    name: str
    character: Character
    position: tuple[int, int]
    current_hp: int
    temp_hp: int
    current_speed: int | None
    reactions_available: int
    guardian_reactions_available: int
    drilled_reaction_available: bool
    shield_raised: bool
    off_guard: bool
    frightened: int
    prone: bool
    actions_remaining: int
    status_bonus_attack: int
    status_bonus_damage: int
    map_count: int = 0
    # Number of attack-trait actions this turn (Strike, Trip, Disarm).
    # Resets to 0 at start of actor's turn. Reactive Strikes use map_count=0.
    conditions: frozenset[str] = frozenset()
    # General-purpose condition/immunity tags ("demoralize_immune", etc.).
    # Does NOT replace existing boolean fields (off_guard, prone, etc.).

    @classmethod
    def from_combatant_state(cls, state: CombatantState) -> CombatantSnapshot:
        """Construct a snapshot from a live CombatantState.

        Resolves current_hp=None to max_hp(character).
        """
        return cls(
            name=state.character.name,
            character=state.character,
            position=state.position,
            current_hp=state.effective_current_hp,
            temp_hp=state.temp_hp,
            current_speed=state.current_speed,
            reactions_available=state.reactions_available,
            guardian_reactions_available=state.guardian_reactions_available,
            drilled_reaction_available=state.drilled_reaction_available,
            shield_raised=state.shield_raised,
            off_guard=state.off_guard,
            frightened=state.frightened,
            prone=state.prone,
            actions_remaining=state.actions_remaining,
            status_bonus_attack=state.status_bonus_attack,
            status_bonus_damage=state.status_bonus_damage,
            map_count=0,
            conditions=frozenset(
                # Auto-deploy Light Mortar at combat start for Inventors.
                # (AoN: https://2e.aonprd.com/Innovations.aspx?ID=4)
                {"mortar_deployed"} if state.character.has_light_mortar
                else set()
            ),
        )


@dataclass(frozen=True)
class EnemySnapshot:
    """Immutable projection of an EnemyState for search branching.

    Dict fields (saves) are immutable-by-convention — don't mutate
    after construction. Use dataclasses.replace() with a new dict.
    """
    name: str
    position: tuple[int, int]
    current_hp: int
    max_hp: int
    ac: int
    saves: dict[SaveType, int]
    attack_bonus: int
    damage_dice: str
    damage_bonus: int
    num_attacks_per_turn: int
    perception_bonus: int
    off_guard: bool
    prone: bool
    actions_remaining: int
    conditions: frozenset[str] = frozenset()
    # General-purpose condition/immunity tags. Same as CombatantSnapshot.
    weaknesses: dict[str, int] = field(default_factory=dict)
    resistances: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_enemy_state(cls, state: EnemyState) -> EnemySnapshot:
        """Construct a snapshot from a live EnemyState."""
        return cls(
            name=state.name,
            position=state.position,
            current_hp=state.effective_current_hp,
            max_hp=state.max_hp,
            ac=state.ac,
            saves=dict(state.saves),
            attack_bonus=state.attack_bonus,
            damage_dice=state.damage_dice,
            damage_bonus=state.damage_bonus,
            num_attacks_per_turn=state.num_attacks_per_turn,
            perception_bonus=state.perception_bonus,
            off_guard=state.off_guard,
            prone=state.prone,
            conditions=frozenset(),
            actions_remaining=state.actions_remaining,
            weaknesses=dict(state.weaknesses),
            resistances=dict(state.resistances),
        )


@dataclass(frozen=True)
class RoundState:
    """Immutable combat state at a point in the search tree.

    Branching creates new instances via with_pc_update / with_enemy_update.
    GridState is shared (effectively immutable post-construction).
    """
    pcs: dict[str, CombatantSnapshot]
    enemies: dict[str, EnemySnapshot]
    initiative_order: tuple[str, ...]
    current_turn_idx: int
    round_number: int
    grid: object  # GridState, but TYPE_CHECKING only to avoid circular
    banner_position: tuple[int, int] | None
    banner_planted: bool
    anthem_active: bool
    branch_probability: float = 1.0

    @classmethod
    def from_scenario(
        cls,
        scenario: Scenario,
        initiative_order: list[str],
    ) -> RoundState:
        """Build initial RoundState from a loaded Scenario."""
        pcs: dict[str, CombatantSnapshot] = {}
        pcs[scenario.commander.character.name] = (
            CombatantSnapshot.from_combatant_state(scenario.commander)
        )
        for sq in scenario.squadmates:
            pcs[sq.character.name] = CombatantSnapshot.from_combatant_state(sq)

        # Apply pre-set conditions from [combatant_state] section
        for name, extra_conds in scenario.combatant_conditions.items():
            if name in pcs:
                pcs[name] = replace(
                    pcs[name],
                    conditions=pcs[name].conditions | extra_conds,
                )

        enemies = {
            e.name: EnemySnapshot.from_enemy_state(e)
            for e in scenario.enemies
        }
        return cls(
            pcs=pcs,
            enemies=enemies,
            initiative_order=tuple(initiative_order),
            current_turn_idx=0,
            round_number=1,
            grid=scenario.grid,
            banner_position=scenario.banner_position,
            banner_planted=scenario.banner_planted,
            anthem_active=scenario.anthem_active,
        )

    def with_pc_update(self, name: str, **changes: object) -> RoundState:
        """Return a new RoundState with one PC's snapshot updated."""
        if name not in self.pcs:
            raise KeyError(f"No PC named {name!r}")
        new_pc = replace(self.pcs[name], **changes)
        new_pcs = dict(self.pcs)
        new_pcs[name] = new_pc
        return replace(self, pcs=new_pcs)

    def with_enemy_update(self, name: str, **changes: object) -> RoundState:
        """Return a new RoundState with one enemy's snapshot updated."""
        if name not in self.enemies:
            raise KeyError(f"No enemy named {name!r}")
        new_enemy = replace(self.enemies[name], **changes)
        new_enemies = dict(self.enemies)
        new_enemies[name] = new_enemy
        return replace(self, enemies=new_enemies)

    def with_branch_probability(self, prob: float) -> RoundState:
        """Return a new RoundState with branch_probability set."""
        return replace(self, branch_probability=prob)
