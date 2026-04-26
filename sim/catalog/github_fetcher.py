"""GitHub fetcher for Foundry pf2e Rule Element data.

Fetches from the Foundry pf2e GitHub repo (v14-dev branch) using only
the standard library. Handles retries with exponential backoff.

Scope for B+.1: flat-path targets only (class-features, bestiary, focus spells).
Nested feat paths (class/level subdirectories) are out of scope.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

FOUNDRY_RAW_BASE = (
    "https://raw.githubusercontent.com/foundryvtt/pf2e/v14-dev/packs/pf2e"
)

USER_AGENT = "pf2e-tactical-simulator/1.0 (github.com/bryan-rt/AI-Dragons)"

# Flat-path packs supported in B+.1
FLAT_PACK_PATHS = [
    "class-features",
    "pathfinder-bestiary",
    "pathfinder-monster-core",
    "pathfinder-bestiary-2",
    "pathfinder-bestiary-3",
    "spells/focus",
]

REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3


def fetch_rule_elements(
    slug: str,
    hint_pack: str | None = None,
) -> dict | None:
    """Fetch Rule Elements for an item by slug from Foundry GitHub.

    Tries hint_pack first if provided, then searches FLAT_PACK_PATHS.
    Returns full item JSON on success, None if not found in any pack.
    Only searches flat-path packs (B+.1 scope). Nested feat paths deferred.
    """
    packs_to_try: list[str] = []
    if hint_pack:
        packs_to_try.append(hint_pack)
    for pack in FLAT_PACK_PATHS:
        if pack not in packs_to_try:
            packs_to_try.append(pack)

    for pack in packs_to_try:
        url = f"{FOUNDRY_RAW_BASE}/{pack}/{slug}.json"
        result = _fetch_url(url)
        if result is not None:
            return result
        time.sleep(REQUEST_DELAY_SECONDS)

    return None


def fetch_bestiary_creature(slug: str) -> dict | None:
    """Fetch a bestiary creature entry by slug.

    Searches bestiary packs in priority order.
    Returns full creature JSON or None if not found.
    """
    bestiary_packs = [
        "pathfinder-bestiary",
        "pathfinder-monster-core",
        "pathfinder-bestiary-2",
        "pathfinder-bestiary-3",
    ]
    for pack in bestiary_packs:
        url = f"{FOUNDRY_RAW_BASE}/{pack}/{slug}.json"
        result = _fetch_url(url)
        if result is not None:
            return result
        time.sleep(REQUEST_DELAY_SECONDS)
    return None


def _fetch_url(url: str, retries: int = MAX_RETRIES) -> dict | None:
    """Fetch a URL with retries. Returns parsed JSON or None on 404."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    return None
