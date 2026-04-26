"""Session initializer for Phase B+ Rule Element cache.

Two-phase init:
  Phase 1 (local): Extract Rule Elements from character JSONs into cache
  Phase 2 (network, optional): Fetch bestiary entries for scenario enemies
"""

from __future__ import annotations

import json
from pathlib import Path

from sim.catalog.github_fetcher import fetch_bestiary_creature
from sim.catalog.session_cache import DEFAULT_CACHE_PATH, SessionCache


def initialize_session(
    character_paths: list[str],
    scenario_path: str | None = None,
    cache_path: str = DEFAULT_CACHE_PATH,
    verbose: bool = True,
) -> SessionCache:
    """Initialize play session by populating Rule Element cache.

    Phase 1: Extract from local character JSONs (no network).
    Phase 2: Fetch bestiary entries for scenario enemies (optional, network).

    Returns the populated SessionCache.
    """
    cache = SessionCache(cache_path)

    # Phase 1: local extraction
    if verbose:
        print("Initializing session cache...")

    char_names: list[str] = []
    local_count = 0
    for char_path in character_paths:
        data = json.loads(Path(char_path).read_text(encoding="utf-8"))
        char_names.append(data.get("name", Path(char_path).stem))
        items = data.get("items", [])
        for item in items:
            slug = _get_slug(item)
            if not slug:
                continue
            item_type = item.get("type", "unknown")
            name = item.get("name", slug)
            rules = item.get("system", {}).get("rules", [])
            if not isinstance(rules, list):
                rules = []
            rule_elements = json.dumps(rules)
            raw_json = json.dumps(item)
            pack = _infer_pack(item_type)

            cache.store_item(
                slug=slug,
                pack=pack,
                item_type=item_type,
                name=name,
                raw_json=raw_json,
                rule_elements=rule_elements,
                source="local",
            )
            local_count += 1

    if verbose:
        print(f"Loading party characters: {', '.join(char_names)}")
        items_summary = cache.list_items()
        with_rules = sum(1 for i in items_summary if i["rule_count"] > 0)
        print(f"Cached {len(items_summary)} unique items from local files "
              f"({with_rules} with Rule Elements)")
        print(f"  ({local_count} total item entries processed, "
              f"{local_count - len(items_summary)} duplicates resolved)")

    # Phase 2: GitHub supplement for scenario enemies (optional)
    if scenario_path:
        enemy_slugs = _extract_enemy_slugs_from_scenario(scenario_path)
        unfetched = [s for s in enemy_slugs if not cache.is_cached(s)]

        if unfetched and verbose:
            print(f"Fetching {len(unfetched)} bestiary entries from GitHub...")

        fetched = 0
        not_found: list[str] = []
        for slug in unfetched:
            result = fetch_bestiary_creature(slug)
            if result is not None:
                rules = result.get("system", {}).get("rules", [])
                if not isinstance(rules, list):
                    rules = []
                cache.store_item(
                    slug=slug,
                    pack="bestiary",
                    item_type="npc",
                    name=result.get("name", slug),
                    raw_json=json.dumps(result),
                    rule_elements=json.dumps(rules),
                    source="github",
                )
                fetched += 1
                if verbose:
                    print(f"  \u2713 {slug} (bestiary)")
            else:
                not_found.append(slug)
                if verbose:
                    print(f"  \u2717 {slug} — not found in bestiary packs")

        if verbose and unfetched:
            print(f"Fetched {fetched}/{len(unfetched)} bestiary entries"
                  + (f" ({len(not_found)} not found)" if not_found else ""))

    # Phase 3: Check for unmodeled Rule Elements (informational only)
    if verbose:
        _check_unmodeled_effects(character_paths, verbose=True)

    if verbose:
        print(f"Session cache ready: {cache._path}")

    return cache


def _get_slug(item: dict) -> str | None:
    """Get slug from item. Prefers system.slug; derives from name as fallback."""
    slug = item.get("system", {}).get("slug")
    if slug:
        return slug
    name = item.get("name", "")
    if not name:
        return None
    slug = name.lower()
    slug = slug.replace("'", "").replace("\u2019", "")
    slug = slug.replace("!", "").replace("(", "").replace(")", "")
    slug = slug.strip().replace(" ", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug or None


def _infer_pack(item_type: str) -> str:
    """Infer Foundry pack name from item type."""
    type_to_pack = {
        "feat": "feats",
        "spell": "spells",
        "action": "actions",
        "class": "classes",
        "ancestry": "ancestries",
        "background": "backgrounds",
        "armor": "equipment",
        "weapon": "equipment",
        "shield": "equipment",
        "equipment": "equipment",
        "lore": "skills",
        "heritage": "heritages",
        "effect": "effects",
    }
    return type_to_pack.get(item_type, item_type)


def _extract_enemy_slugs_from_scenario(scenario_path: str) -> list[str]:
    """Extract enemy name slugs from a scenario file.

    Reads the [enemies] section and derives slugs from the name= values.
    Scenario format: `m1 name=Bandit1 ac=15 ref=5 fort=3 will=2`
    """
    slugs: list[str] = []
    try:
        text = Path(scenario_path).read_text(encoding="utf-8")
    except (FileNotFoundError, IOError):
        return slugs

    in_enemies = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[enemies]":
            in_enemies = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_enemies = False
            continue
        if not in_enemies or not stripped or stripped.startswith("#"):
            continue
        # Parse key=value pairs to find name=
        for part in stripped.split():
            if part.lower().startswith("name="):
                name = part.split("=", 1)[1]
                slug = name.lower().replace(" ", "-")
                slugs.append(slug)
                break
    return slugs


# ---------------------------------------------------------------------------
# Unmodeled effects check (B+.2)
# ---------------------------------------------------------------------------

# Rule Element kinds already handled by the importer or engine, or verified
# as non-combat / creation-time only. Each entry has a comment explaining WHY
# it's safe to skip.
_HANDLED_KINDS: set[str] = {
    # Combat-relevant, explicitly handled in engine:
    "Resistance",       # guardians_armor_resistance() in combat_math.py
    "Aura",             # Commander's Banner aura modeled in tactics system
    "FlatModifier",     # Nimble Elf → _derive_speed() adds +5;
                        # Commander's Banner fear bonus → enemies don't use fear yet;
                        # Torch fire +1 → improvised weapon, not combat-relevant
    # Creation-time stat mutations already captured by the importer:
    "ActiveEffectLike", # All 12 instances verified (B+.2 Pass 1):
                        #   - Skill rank upgrades (Crafting, Arcana) → _extract_skills()
                        #   - Foundry internal flags (innovationId, explode type, enhancements)
                        #   - Inventory capacity (Hefty Hauler) → non-combat
                        #   - Light Mortar class DC scaling → not relevant until L7 (CP8)
    "AdjustModifier",   # All 4 instances verified (B+.2 Pass 1):
                        #   - Subterfuge Suit AC downgrade → predicate FALSE for Aetregan
                        #     (has Armor Innovation feature, so downgrade does not apply)
                        #   - Compass → suppresses navigation penalty, non-combat
                        #   - Commander's Banner Glorious → requires Glorious Banner feat
                        #     not present in party
                        #   - Assurance suppress-modifiers → paired with SubstituteRoll
    "Strike",           # Torch (improvised weapon, never optimal) and
                        # Warrior Automaton fist (d4 unarmed, Rook has Earthbreaker d6)
    # Creation-time / UI only — no combat impact:
    "GrantItem",        # Grants other items during character build
    "ChoiceSet",        # Presents build choices during character creation
    "Note",             # UI annotation text (tooltips, reminders)
    "RollOption",       # Sets predicate flags for conditional Rule Elements
    "TokenLight",       # Visual token lighting effects
    "TokenEffectIcon",  # Visual token effect icons
    "ItemAlteration",   # Modifies item properties at creation time
    "CreatureSize",     # Sets creature size category (already derived from ancestry)
}

# Rule Elements that are genuinely unmodeled but documented as non-blocking.
# Maps kind → human-readable explanation for the warning message.
_UNMODELED_BUT_KNOWN: dict[str, str] = {
    "SubstituteRoll": "Assurance — replaces d20 with 10+prof (no combat impact at L1)",
}


def _check_unmodeled_effects(
    character_paths: list[str],
    verbose: bool = True,
) -> list[tuple[str, str, str]]:
    """Scan character items for unmodeled Rule Elements. Informational only.

    Returns list of (character_name, item_name, description) tuples for
    any Rule Elements whose kind is not in _HANDLED_KINDS.
    Never raises, never blocks session init (Option B: core-complete).
    """
    results: list[tuple[str, str, str]] = []

    for char_path in character_paths:
        try:
            data = json.loads(Path(char_path).read_text(encoding="utf-8"))
        except (FileNotFoundError, IOError, json.JSONDecodeError):
            continue

        char_name = data.get("name", Path(char_path).stem)
        unmodeled: list[str] = []

        for item in data.get("items", []):
            item_name = item.get("name", "?")
            for rule in item.get("system", {}).get("rules", []):
                kind = rule.get("key", "")
                if not kind or kind in _HANDLED_KINDS:
                    continue
                note = _UNMODELED_BUT_KNOWN.get(kind, "no handler")
                unmodeled.append(f"  - {item_name}: {kind} ({note})")
                results.append((char_name, item_name, f"{kind} ({note})"))

        if unmodeled and verbose:
            print(f"[INFO] {char_name}: {len(unmodeled)} unmodeled Rule Element(s) "
                  f"(non-blocking):")
            for line in unmodeled:
                print(line)

    return results
