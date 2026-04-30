"""Scenario file loading: text -> fully-wired TacticContext.

A scenario file bundles grid terrain, party positions, enemy stats,
banner state, and anthem state. load_scenario() reads from disk;
parse_scenario() parses a string. Both produce a Scenario object,
which exposes build_tactic_context() for evaluation.

File format (see scenarios/*.scenario for examples):

    [meta]
    name = <description>
    level = <int>
    source = <citation>
    description = <long text>

    [grid]
    <ASCII grid with tokens separated by whitespace>

    [banner]
    planted = true | false
    position = <row>, <col>

    [anthem]
    active = true | false

    [enemies]
    <token> name=<word> ac=<int> ref=<int> fort=<int> will=<int>

Enemy tokens in [enemies] use the auto-numbered form from the grid
parser (e.g., m1, m2, M1), never the bare letter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pf2e.character import CombatantState, EnemyState
from pf2e.detection import LightLevel, LightSource
from pf2e.tactics import TacticContext
from pf2e.types import Ability, SaveType
from sim.grid import GridState, Pos, parse_map
from sim.grid_spatial import GridSpatialQueries
from sim.party import (
    COMMANDER_TOKEN,
    SQUADMATE_TOKENS,
    TOKEN_TO_FACTORY,
    make_rook_combat_state,
)


class ScenarioParseError(Exception):
    """Raised when a scenario file/string cannot be parsed."""


# ---------------------------------------------------------------------------
# Scenario dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    """A fully-loaded combat scenario, ready to produce a TacticContext.

    Frozen — scenarios are built once from a file and don't change.
    CombatantState objects inside are mutable (for transient state like
    reactions), but the Scenario wrapper itself cannot be reassigned.
    """
    name: str
    level: int
    source: str
    description: str

    grid: GridState
    banner_position: Pos | None
    banner_planted: bool

    anthem_active: bool

    commander: CombatantState
    squadmates: list[CombatantState]
    enemies: list[EnemyState]

    # Initiative specification (Pass 3b uses this to roll/sort)
    initiative_seed: int = 42
    initiative_explicit: dict[str, int] = field(default_factory=dict)

    # Pre-set conditions per combatant name (from [combatant_state] section).
    # Applied to CombatantSnapshot.conditions during RoundState construction.
    combatant_conditions: dict[str, frozenset[str]] = field(default_factory=dict)

    # Lighting (CP10.7)
    ambient_light: LightLevel = LightLevel.BRIGHT
    light_sources: tuple[LightSource, ...] = ()

    def build_tactic_context(self) -> TacticContext:
        """Produce a fresh TacticContext with GridSpatialQueries wired in.

        Constructs a new GridSpatialQueries each call. Safe to call
        multiple times; the returned contexts are independent.
        """
        spatial = GridSpatialQueries(
            grid_state=self.grid,
            commander=self.commander,
            squadmates=list(self.squadmates),
            enemies=list(self.enemies),
            banner_position=self.banner_position,
            banner_planted=self.banner_planted,
        )
        return TacticContext(
            commander=self.commander,
            squadmates=list(self.squadmates),
            enemies=list(self.enemies),
            banner_position=self.banner_position,
            banner_planted=self.banner_planted,
            spatial=spatial,
            anthem_active=self.anthem_active,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ENEMY_TOKEN_RE = re.compile(r"^[mM]\d+$")


def _build_combatant(
    token: str, pos: Pos, anthem_active: bool,
) -> CombatantState:
    """Build a CombatantState from a grid token + position.

    Rook (token 'g') uses make_rook_combat_state() which applies the
    full plate speed penalty. All others use from_character() directly.
    """
    if token == "g":
        state = make_rook_combat_state(anthem_active=anthem_active)
        state.position = pos
    else:
        factory = TOKEN_TO_FACTORY[token]
        state = CombatantState.from_character(
            factory(), position=pos, anthem_active=anthem_active,
        )
    return state


def _build_enemy(
    token: str, spec: dict[str, str], pos: Pos,
) -> EnemyState:
    """Build an EnemyState from parsed key=value spec.

    If spec contains 'sheet=<slug>', loads the NPC JSON and builds
    EnemyState from pre-calculated stats. Otherwise uses flat-stat path.
    """
    if "sheet" in spec:
        return _build_enemy_from_sheet(token, spec, pos)
    required = ("name", "ac", "ref", "fort", "will")
    missing = [k for k in required if k not in spec]
    if missing:
        raise ScenarioParseError(
            f"Enemy '{token}' missing required fields: {missing}"
        )
    try:
        # Parse weakness_<type>=<int> and resistance_<type>=<int> keys
        weaknesses: dict[str, int] = {}
        resistances: dict[str, int] = {}
        for key, val in spec.items():
            if key.startswith("weakness_"):
                dmg_type = key[len("weakness_"):]
                weaknesses[dmg_type] = int(val)
            elif key.startswith("resistance_"):
                dmg_type = key[len("resistance_"):]
                resistances[dmg_type] = int(val)

        return EnemyState(
            name=spec["name"],
            ac=int(spec["ac"]),
            saves={
                SaveType.REFLEX: int(spec["ref"]),
                SaveType.FORTITUDE: int(spec["fort"]),
                SaveType.WILL: int(spec["will"]),
            },
            position=pos,
            off_guard=spec.get("off_guard", "false").lower() == "true",
            prone=spec.get("prone", "false").lower() == "true",
            attack_bonus=int(spec.get("atk", "0")),
            damage_dice=spec.get("dmg", ""),
            damage_bonus=int(spec.get("dmg_bonus", "0")),
            num_attacks_per_turn=int(spec.get("attacks", "2")),
            max_hp=int(spec.get("max_hp", "20")),
            perception_bonus=int(spec.get("perception", "4")),
            weaknesses=weaknesses,
            resistances=resistances,
        )
    except ValueError as e:
        raise ScenarioParseError(
            f"Enemy '{token}': invalid integer in stats: {e}"
        ) from e


def _build_enemy_from_sheet(
    token: str, spec: dict[str, str], pos: Pos,
) -> EnemyState:
    """Build EnemyState from a Foundry NPC JSON sheet reference.

    Spec must contain sheet=<slug>. Resolves to
    characters/enemies/<slug>.json. Optional name= overrides the
    JSON name.
    """
    from pathlib import Path
    from sim.importers.foundry_npc import import_foundry_npc

    slug = spec["sheet"]
    search_paths = [
        Path("characters/enemies") / f"{slug}.json",
        Path(slug) if slug.endswith(".json") else None,
    ]
    json_path = next(
        (p for p in search_paths if p is not None and p.exists()), None)
    if json_path is None:
        raise ScenarioParseError(
            f"Enemy sheet not found: '{slug}'. "
            f"Expected at characters/enemies/{slug}.json"
        )

    npc = import_foundry_npc(str(json_path))
    name = spec.get("name", npc.name)

    # Derive flat stats from NPCData for EnemyState compatibility
    best_atk = max(npc._attack_totals.values(), default=0)
    first_weapon = (npc.equipped_weapons[0]
                    if npc.equipped_weapons else None)
    dmg_die = first_weapon.weapon.damage_die if first_weapon else "1d4"
    dmg_die_count = (first_weapon.weapon.damage_die_count
                     if first_weapon else 1)
    dmg_dice_str = (f"{dmg_die_count}{dmg_die}"
                    if dmg_die_count > 0 else "1d4")
    dmg_bonus = 0
    if first_weapon:
        dmg_bonus = npc.abilities.mod(Ability.STR)

    return EnemyState(
        name=name,
        ac=npc._ac_total,
        saves=dict(npc._save_totals),
        position=pos,
        attack_bonus=best_atk,
        damage_dice=dmg_dice_str,
        damage_bonus=dmg_bonus,
        num_attacks_per_turn=min(len(npc.equipped_weapons), 3) or 1,
        max_hp=npc._max_hp,
        current_hp=npc._max_hp,
        perception_bonus=npc._perception_total,
        weaknesses={},
        resistances={},
        character=npc,
    )


def _split_into_sections(text: str) -> dict[str, str]:
    """Split scenario text into {section_name: content_string}."""
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip().lower()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    return {k: "\n".join(v) for k, v in sections.items()}


def _parse_meta(text: str) -> dict[str, str]:
    """Parse [meta] section into key=value dict."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip().lower()] = value.strip()
    return result


def _parse_banner(
    text: str | None, grid_fallback_pos: Pos | None,
) -> tuple[Pos | None, bool]:
    """Parse [banner] section. Falls back to grid token if no section."""
    if not text:
        if grid_fallback_pos is not None:
            return grid_fallback_pos, True
        return None, False

    kv = _parse_meta(text)

    planted_str = kv.get("planted", "true").lower()
    if planted_str not in ("true", "false"):
        raise ScenarioParseError(
            f"[banner] planted must be 'true' or 'false', got '{planted_str}'"
        )
    planted = planted_str == "true"

    pos_str = kv.get("position")
    if pos_str is None:
        if planted:
            raise ScenarioParseError(
                "[banner] section with planted=true requires 'position = row, col'"
            )
        # Carried banner: position is optional (aura follows commander)
        return None, False

    try:
        parts = pos_str.split(",")
        pos: Pos = (int(parts[0].strip()), int(parts[1].strip()))
    except (ValueError, IndexError) as e:
        raise ScenarioParseError(
            f"[banner] invalid position '{pos_str}': {e}"
        ) from e

    return pos, planted


def _parse_anthem(text: str | None) -> bool:
    """Parse [anthem] section. Default: inactive."""
    if not text:
        return False
    kv = _parse_meta(text)
    return kv.get("active", "false").lower() == "true"


def _parse_enemies(text: str) -> dict[str, dict[str, str]]:
    """Parse [enemies] section into {token: {key: value}} dict."""
    result: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if not parts:
            continue
        token = parts[0]
        spec: dict[str, str] = {}
        for part in parts[1:]:
            if "=" not in part:
                raise ScenarioParseError(
                    f"[enemies] malformed key=value pair: '{part}' "
                    f"in line: {line}"
                )
            k, _, v = part.partition("=")
            spec[k.strip().lower()] = v.strip()
        result[token] = spec
    return result


def _parse_initiative(text: str | None) -> tuple[int, dict[str, int]]:
    """Parse [initiative] section.

    Supports seed-only or explicit ordering.
    Returns (seed, explicit_dict). If section omitted, returns (42, {}).
    """
    if not text:
        return (42, {})

    seed = 42
    explicit: dict[str, int] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if key.lower() == "seed":
            try:
                seed = int(value)
            except ValueError as e:
                raise ScenarioParseError(
                    f"[initiative] seed must be an integer: {value}"
                ) from e
        else:
            try:
                explicit[key] = int(value)
            except ValueError as e:
                raise ScenarioParseError(
                    f"[initiative] '{key}' must be an integer: {value}"
                ) from e

    return (seed, explicit)


def _parse_combatant_state(text: str | None) -> dict[str, frozenset[str]]:
    """Parse [combatant_state] section into {name: frozenset of condition tags}.

    Format: one line per combatant, comma-separated tags.
        Erisen = mortar_aimed, mortar_loaded
    """
    if not text:
        return {}
    result: dict[str, frozenset[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        name, _, tags_str = line.partition("=")
        name = name.strip()
        tags = frozenset(
            t.strip() for t in tags_str.split(",") if t.strip()
        )
        if tags:
            result[name] = tags
    return result


_LIGHT_SOURCE_SPECS: dict[str, tuple[int, int]] = {
    "campfire": (20, 40),
    "torch": (20, 40),
    "dancing_lights": (0, 20),
}


def _parse_lighting(
    text: str | None,
) -> tuple[LightLevel, tuple[LightSource, ...]]:
    """Parse [lighting] section. Returns (ambient, light_sources).

    Format:
        ambient = dim
        campfire = 5,8
        torch = 3,4
    """
    if not text:
        return (LightLevel.BRIGHT, ())

    ambient = LightLevel.BRIGHT
    sources: list[LightSource] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip()

        if key == "ambient":
            try:
                ambient = LightLevel(value.lower())
            except ValueError:
                raise ScenarioParseError(
                    f"[lighting] invalid ambient: {value!r} "
                    f"(expected bright/dim/dark)"
                )
        elif key in _LIGHT_SOURCE_SPECS:
            bright_ft, dim_ft = _LIGHT_SOURCE_SPECS[key]
            try:
                parts = value.split(",")
                pos = (int(parts[0].strip()), int(parts[1].strip()))
            except (IndexError, ValueError) as e:
                raise ScenarioParseError(
                    f"[lighting] invalid position for {key}: {value!r}"
                ) from e
            sources.append(LightSource(
                position=pos,
                bright_radius_ft=bright_ft,
                dim_radius_ft=dim_ft,
                name=key,
            ))

    return (ambient, tuple(sources))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_scenario(path: str | Path) -> Scenario:
    """Read and parse a scenario file from disk.

    Raises:
        FileNotFoundError: if the file doesn't exist.
        ScenarioParseError: if the content is malformed.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_scenario(text)


def parse_scenario(text: str) -> Scenario:
    """Parse scenario text into a Scenario object.

    Raises:
        ScenarioParseError: if the content is malformed.
    """
    sections = _split_into_sections(text)

    # Required: [grid]
    if "grid" not in sections:
        raise ScenarioParseError("Missing required [grid] section")

    meta = _parse_meta(sections.get("meta", ""))
    grid, positions, grid_banner_pos = parse_map(sections["grid"])
    banner_pos, banner_planted = _parse_banner(
        sections.get("banner"), grid_banner_pos,
    )
    anthem_active = _parse_anthem(sections.get("anthem"))
    enemy_specs = _parse_enemies(sections.get("enemies", ""))
    initiative_seed, initiative_explicit = _parse_initiative(
        sections.get("initiative"),
    )
    combatant_conditions = _parse_combatant_state(
        sections.get("combatant_state"),
    )
    ambient_light, light_sources = _parse_lighting(
        sections.get("lighting"),
    )

    # Commander required
    if COMMANDER_TOKEN not in positions:
        raise ScenarioParseError(
            f"No commander ({COMMANDER_TOKEN!r}) token found in grid"
        )

    # Identify enemy tokens in the grid (auto-numbered: m1, m2, M1, etc.)
    grid_enemy_tokens = {
        t for t in positions if _ENEMY_TOKEN_RE.match(t)
    }

    # Validate enemy tokens match between grid and [enemies] section
    missing_stats = grid_enemy_tokens - enemy_specs.keys()
    missing_grid = enemy_specs.keys() - grid_enemy_tokens
    if missing_stats:
        raise ScenarioParseError(
            f"Enemy tokens in grid with no [enemies] stats: "
            f"{sorted(missing_stats)}"
        )
    if missing_grid:
        raise ScenarioParseError(
            f"[enemies] entries with no grid token: "
            f"{sorted(missing_grid)}"
        )

    # Build party
    commander = _build_combatant(
        COMMANDER_TOKEN, positions[COMMANDER_TOKEN], anthem_active,
    )
    squadmates = [
        _build_combatant(tok, positions[tok], anthem_active)
        for tok in SQUADMATE_TOKENS
        if tok in positions
    ]

    # Build enemies
    enemies = [
        _build_enemy(token, spec, positions[token])
        for token, spec in enemy_specs.items()
    ]

    return Scenario(
        name=meta.get("name", "Untitled"),
        level=int(meta.get("level", "1")),
        source=meta.get("source", ""),
        description=meta.get("description", ""),
        grid=grid,
        banner_position=banner_pos,
        banner_planted=banner_planted,
        anthem_active=anthem_active,
        commander=commander,
        squadmates=squadmates,
        enemies=enemies,
        initiative_seed=initiative_seed,
        initiative_explicit=initiative_explicit,
        combatant_conditions=combatant_conditions,
        ambient_light=ambient_light,
        light_sources=light_sources,
    )
