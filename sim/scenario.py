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
from dataclasses import dataclass
from pathlib import Path

from pf2e.character import CombatantState, EnemyState
from pf2e.tactics import TacticContext
from pf2e.types import SaveType
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
    """Build an EnemyState from parsed key=value spec."""
    required = ("name", "ac", "ref", "fort", "will")
    missing = [k for k in required if k not in spec]
    if missing:
        raise ScenarioParseError(
            f"Enemy '{token}' missing required fields: {missing}"
        )
    try:
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
        )
    except ValueError as e:
        raise ScenarioParseError(
            f"Enemy '{token}': invalid integer in stats: {e}"
        ) from e


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
    if not planted:
        raise ScenarioParseError(
            "Carried banner (planted=false) is not yet supported. "
            "Use planted=true for Checkpoint 3."
        )

    pos_str = kv.get("position")
    if pos_str is None:
        raise ScenarioParseError("[banner] section requires 'position = row, col'")
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
    )
