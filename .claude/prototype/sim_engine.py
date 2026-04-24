"""
Map representation, action economy, and tactic simulation for PF2e.
Tactics are the Commander's level-1 toolkit. Simulator runs one full round.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable
from copy import deepcopy
from characters import (
    Character, Strike,
    expected_strike_damage, expected_aoe_damage,
)


# ---------- MAP HELPERS ----------

def parse_map(grid_str: str) -> dict:
    """
    Parse a multi-line map string. Each cell is a character or 2-char token.
    Recognized tokens:
        '.' or ' '   = empty
        'c'          = commander (Aetregan)
        'g'          = guardian (Rook)
        'b'          = bard (Dalai)
        'i'          = inventor (Erisen)
        'm'          = enemy minion
        'M'          = enemy brute
        'B'          = banner
    Returns {char_label: (row, col), ...} and 'banner': pos.
    """
    positions = {}
    rows = [line for line in grid_str.strip().split("\n") if line.strip()]
    for r, line in enumerate(rows):
        cells = line.replace("|", " ").split()
        for c, cell in enumerate(cells):
            cell = cell.strip(".-")
            if not cell:
                continue
            if cell in positions:
                # multiple of same kind → number them
                i = 2
                while f"{cell}{i}" in positions:
                    i += 1
                positions[f"{cell}{i}"] = (r, c)
            else:
                positions[cell] = (r, c)
    return positions


def render_map(characters: List[Character], banner_pos=None,
               grid_size=(10, 10)) -> str:
    """ASCII render of map state."""
    grid = [["." for _ in range(grid_size[1])] for _ in range(grid_size[0])]
    if banner_pos:
        r, c = banner_pos
        if 0 <= r < grid_size[0] and 0 <= c < grid_size[1]:
            grid[r][c] = "B"
    for char in characters:
        r, c = char.pos
        if 0 <= r < grid_size[0] and 0 <= c < grid_size[1]:
            tag = char.name[0].lower() if char.role != "enemy" else char.name[0]
            grid[r][c] = tag
    header = "   " + " ".join(str(i) for i in range(grid_size[1]))
    rows = [header]
    for i, row in enumerate(grid):
        rows.append(f"{i:2d} " + " ".join(row))
    return "\n".join(rows)


def squares_in_burst(center: tuple, burst_radius_ft: int) -> set:
    """All squares within a burst (radius_ft / 5 squares)."""
    radius = burst_radius_ft // 5
    cr, cc = center
    return {(cr + dr, cc + dc)
            for dr in range(-radius, radius + 1)
            for dc in range(-radius, radius + 1)}


def chars_in_burst(characters: List[Character], center: tuple,
                   burst_ft: int) -> List[Character]:
    burst = squares_in_burst(center, burst_ft)
    return [c for c in characters if c.pos in burst]


def in_banner_aura(char: Character, banner_pos: tuple,
                   aura_ft: int = 30) -> bool:
    if banner_pos is None:
        return False
    dr = abs(char.pos[0] - banner_pos[0])
    dc = abs(char.pos[1] - banner_pos[1])
    return max(dr, dc) * 5 <= aura_ft


# ---------- COMBAT MATH SHORTCUTS ----------

def strike_against(attacker: Character, target: Character,
                   off_guard: bool = False, map_penalty: int = 0,
                   strike_idx: int = 0) -> float:
    """Expected damage of one strike. Returns 0 if out of reach."""
    if strike_idx >= len(attacker.strikes):
        return 0
    s = attacker.strikes[strike_idx]
    if attacker.distance_to(target) > s.reach and not s.is_ranged:
        return 0
    return expected_strike_damage(
        attack_bonus=s.attack_bonus,
        target_ac=target.ac,
        damage_avg=s.damage_avg,
        off_guard=off_guard,
        map_penalty=map_penalty,
    )


def adjacent_enemies(char: Character,
                     all_chars: List[Character]) -> List[Character]:
    """Enemies within 5 ft (adjacent in 8 directions)."""
    return [other for other in all_chars
            if other.role == "enemy"
            and other is not char
            and char.distance_to(other) <= 5]


def enemies_within_reach(char: Character, all_chars: List[Character],
                         reach_ft: int = 5) -> List[Character]:
    return [other for other in all_chars
            if other.role == "enemy"
            and char.distance_to(other) <= reach_ft]


def enemies_in_strike_reach(char: Character,
                            all_chars: List[Character]) -> List[Character]:
    """Enemies within the character's longest melee reach."""
    if not char.strikes:
        return []
    max_reach = max(s.reach for s in char.strikes if not s.is_ranged) \
        if any(not s.is_ranged for s in char.strikes) else 0
    return enemies_within_reach(char, all_chars, max_reach)


# ---------- MORTAR HANDLING ----------

@dataclass
class MortarState:
    """Tracks Erisen's mortar across a turn."""
    deployed: bool = True   # assume deployed at scenario start
    aimed: bool = False     # set after Aim action
    aim_point: Optional[tuple] = None
    loaded: bool = True     # assume loaded at scenario start
    damage_dice_avg: float = 7.0  # 2d6 = 7 avg at level 1
    burst_ft: int = 10
    save_dc: int = 17       # Erisen's class DC at level 1
    moves_invalidate_aim: bool = True


def mortar_total_expected_damage(mortar: MortarState, target_pos: tuple,
                                 all_chars: List[Character],
                                 friendlies_count_as_negative: bool = True
                                 ) -> dict:
    """
    Returns expected damage info for a mortar shot at target_pos.
    Returns {'enemy_dmg': float, 'friendly_dmg': float, 'targets_hit': [...]}
    """
    affected = chars_in_burst(all_chars, target_pos, mortar.burst_ft)
    enemy_dmg = 0
    friendly_dmg = 0
    targets_hit = []
    for c in affected:
        dmg = expected_aoe_damage(
            damage_avg=mortar.damage_dice_avg,
            save_bonus=c.refl,
            dc=mortar.save_dc,
        )
        targets_hit.append((c.name, dmg, c.role))
        if c.role == "enemy":
            enemy_dmg += dmg
        else:
            friendly_dmg += dmg
    return {
        "enemy_dmg": enemy_dmg,
        "friendly_dmg": friendly_dmg,
        "targets_hit": targets_hit,
        "net_dmg": enemy_dmg - friendly_dmg,
    }


def best_mortar_target(mortar: MortarState, all_chars: List[Character],
                       max_range: int = 600) -> dict:
    """Search nearby grid squares to find the highest net-damage target square."""
    enemies = [c for c in all_chars if c.role == "enemy"]
    if not enemies:
        return {"enemy_dmg": 0, "friendly_dmg": 0, "targets_hit": [],
                "net_dmg": 0, "target_pos": None}
    # Try enemy positions and squares between clustered enemies
    candidates = set()
    for e in enemies:
        candidates.add(e.pos)
        # also try adjacent squares for better cluster centering
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                candidates.add((e.pos[0] + dr, e.pos[1] + dc))
    best = None
    for pos in candidates:
        result = mortar_total_expected_damage(mortar, pos, all_chars)
        result["target_pos"] = pos
        if best is None or result["net_dmg"] > best["net_dmg"]:
            best = result
    return best


# ---------- ENEMY THREAT MODEL ----------

def expected_enemy_damage_to_party(enemies: List[Character],
                                   party: List[Character],
                                   actions_per_enemy: int = 3) -> float:
    """
    Estimate how much damage enemies will deal in their turns.
    Each enemy will move toward the closest squishy target and attack.
    """
    total = 0
    for enemy in enemies:
        if not enemy.strikes:
            continue
        # Pick lowest-HP party member they can reach in `actions_per_enemy - 1` strides
        reachable = [(p, enemy.distance_to(p)) for p in party]
        reachable.sort(key=lambda x: (x[1], x[0].hp))
        if not reachable:
            continue
        target, dist = reachable[0]
        squares_needed = max(0, (dist - enemy.strikes[0].reach) // 5)
        moves_needed = squares_needed * 5 // enemy.speed + (
            1 if squares_needed * 5 % enemy.speed else 0)
        attack_actions = actions_per_enemy - moves_needed
        if attack_actions <= 0:
            continue
        # MAP penalties: 0, 5, 10
        map_penalties = [0, 5, 10][:attack_actions]
        for mp in map_penalties:
            total += strike_against(enemy, target, map_penalty=mp)
    return total


# ---------- TACTICS ----------

@dataclass
class TacticResult:
    name: str
    description: str
    damage_dealt: float
    damage_taken_estimate: float
    notes: List[str] = field(default_factory=list)
    actions_used: int = 0

    @property
    def net_value(self) -> float:
        return self.damage_dealt - self.damage_taken_estimate


def tactic_strike_hard(commander: Character, target_ally: Character,
                       enemies: List[Character], all_chars: List[Character],
                       banner_pos: tuple) -> TacticResult:
    """1 action. Ally Strikes as a reaction (no MAP). Best vs single tough target."""
    if not in_banner_aura(target_ally, banner_pos):
        return TacticResult("Strike Hard! (FAILED)",
                            f"{target_ally.name} not in banner aura.",
                            0, 0, ["Out of aura"], 1)
    reach_targets = enemies_in_strike_reach(target_ally, all_chars)
    if not reach_targets:
        return TacticResult("Strike Hard! (FAILED)",
                            f"{target_ally.name} has no enemies in reach.",
                            0, 0, ["No targets"], 1)
    best_target = max(reach_targets,
                      key=lambda e: strike_against(target_ally, e))
    dmg = strike_against(target_ally, best_target)
    return TacticResult(
        "Strike Hard!",
        f"{target_ally.name} reaction-Strikes {best_target.name} for ~{dmg:.1f}",
        damage_dealt=dmg,
        damage_taken_estimate=0,
        notes=[f"Reaction Strike at +{target_ally.strikes[0].attack_bonus} "
               f"vs AC {best_target.ac}"],
        actions_used=1,
    )


def tactic_gather_to_me(commander: Character,
                        squadmates: List[Character],
                        enemies: List[Character],
                        all_chars: List[Character],
                        banner_pos: tuple,
                        mortar: Optional[MortarState] = None,
                        mortar_target: Optional[tuple] = None
                        ) -> TacticResult:
    """1 action. All squadmates Stride toward banner aura.
    Used to clear allies out of mortar AoE."""
    notes = []
    cleared_friendly_dmg = 0

    if mortar and mortar_target:
        # Calc original friendly fire
        original = mortar_total_expected_damage(mortar, mortar_target, all_chars)
        original_friendly = original["friendly_dmg"]
        # Move squadmates out: assume they reach safe distance
        moved_chars = deepcopy(all_chars)
        burst = squares_in_burst(mortar_target, mortar.burst_ft)
        for c in moved_chars:
            if c.is_squadmate and c.pos in burst and c.role != "commander":
                # Move to nearest square outside burst, near banner
                # Simplified: just remove from burst by shifting toward banner
                br, bc = banner_pos
                dr = -1 if c.pos[0] > br else (1 if c.pos[0] < br else 0)
                dc = -1 if c.pos[1] > bc else (1 if c.pos[1] < bc else 0)
                steps = c.speed // 5
                new_pos = (c.pos[0] + dr * steps, c.pos[1] + dc * steps)
                c.pos = new_pos
        new_result = mortar_total_expected_damage(mortar, mortar_target, moved_chars)
        cleared_friendly_dmg = original_friendly - new_result["friendly_dmg"]
        notes.append(f"Mortar shot now spares ~{cleared_friendly_dmg:.1f} friendly dmg")
        notes.append(f"Mortar enemy dmg: {new_result['enemy_dmg']:.1f}")
        damage_dealt = new_result["enemy_dmg"]
    else:
        damage_dealt = 0
        notes.append("No mortar shot specified — Gather to Me has no AoE benefit")

    return TacticResult(
        "Gather to Me!",
        "Squadmates Stride toward banner aura (clear AoE / regroup)",
        damage_dealt=damage_dealt,
        damage_taken_estimate=-cleared_friendly_dmg,  # negative = damage avoided
        notes=notes,
        actions_used=1,
    )


def tactic_tactical_takedown(commander: Character,
                             squadmates: List[Character],
                             enemies: List[Character],
                             all_chars: List[Character],
                             banner_pos: tuple) -> TacticResult:
    """2 actions. Two squadmates Stride half speed. If both end adjacent
    to an enemy, that enemy must save vs Reflex DC or fall prone."""
    available = [s for s in squadmates
                 if in_banner_aura(s, banner_pos) and s != commander]
    if len(available) < 2:
        return TacticResult("Tactical Takedown (FAILED)",
                            "Need 2 squadmates in aura",
                            0, 0, ["Insufficient squadmates"], 2)
    # Try to find an enemy that 2 squadmates can both reach with half-speed Stride
    for enemy in enemies:
        adjacent_squares = [(enemy.pos[0] + dr, enemy.pos[1] + dc)
                            for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                            if (dr, dc) != (0, 0)]
        reachers = []
        for sq in available:
            half_speed = sq.speed // 2
            for adj in adjacent_squares:
                dist = max(abs(sq.pos[0] - adj[0]), abs(sq.pos[1] - adj[1])) * 5
                if dist <= half_speed:
                    reachers.append((sq, adj))
                    break
        if len(reachers) >= 2:
            # Found valid pairing
            # Prone enemy = off-guard. Estimate prone success: DC 17 vs typical mook +5 Refl
            # Save chance: 12+ on d20 = 45% success, 15% crit save
            # Fail = 35%, crit fail = 5% → prone outcomes: 40% chance prone
            prone_chance = 0.40
            # Damage from one follow-up Strike with off-guard
            best_attacker = max(reachers,
                key=lambda r: strike_against(r[0], enemy, off_guard=True))[0]
            extra_dmg = prone_chance * strike_against(
                best_attacker, enemy, off_guard=True)
            return TacticResult(
                "Tactical Takedown",
                f"{reachers[0][0].name} & {reachers[1][0].name} Stride to flank "
                f"{enemy.name} (Refl DC vs prone, ~40% chance)",
                damage_dealt=extra_dmg,
                damage_taken_estimate=0,
                notes=[f"Sets up off-guard for follow-up attacks (+~{extra_dmg:.1f})"],
                actions_used=2,
            )
    return TacticResult("Tactical Takedown (FAILED)",
                        "No enemy reachable by 2 squadmates",
                        0, 0, ["No valid pairing"], 2)


def tactic_defensive_retreat(commander: Character,
                             squadmates: List[Character],
                             enemies: List[Character],
                             all_chars: List[Character],
                             banner_pos: tuple) -> TacticResult:
    """2 actions. Squadmates Step 3 times away from enemies.
    Reduces incoming damage by forcing enemies to spend actions catching up."""
    in_aura = [s for s in squadmates if in_banner_aura(s, banner_pos)]
    enemies_engaging = [
        s for s in in_aura
        if any(s.distance_to(e) <= 10 for e in enemies)
    ]
    if not enemies_engaging:
        return TacticResult("Defensive Retreat (FAILED)",
                            "No squadmates engaged by enemies",
                            0, 0, ["No threats to retreat from"], 2)
    # Each engaged squadmate steps 15 ft away → enemies spend ~1 extra action moving
    saved_dmg = 0
    for sq in enemies_engaging:
        threats = [e for e in enemies if sq.distance_to(e) <= 10]
        for threat in threats:
            # Threat loses ~1 action of attack worth of damage
            saved_dmg += strike_against(threat, sq, map_penalty=5) * 0.5
    return TacticResult(
        "Defensive Retreat",
        f"{len(enemies_engaging)} squadmates Step away from enemies",
        damage_dealt=0,
        damage_taken_estimate=-saved_dmg,
        notes=[f"Enemies forced to use actions chasing → ~{saved_dmg:.1f} dmg avoided"],
        actions_used=2,
    )


def tactic_form_up(commander: Character, squadmates: List[Character],
                   enemies: List[Character], all_chars: List[Character],
                   banner_pos: tuple) -> TacticResult:
    """Placeholder — Form Up isn't a level-1 tactic. Skipping for now."""
    return TacticResult("Form Up (n/a)", "Not a base tactic", 0, 0, [], 0)


# Tactic registry — only level-1 tactics from your folio
TACTICS = {
    "strike_hard": tactic_strike_hard,
    "gather_to_me": tactic_gather_to_me,
    "tactical_takedown": tactic_tactical_takedown,
    "defensive_retreat": tactic_defensive_retreat,
}
