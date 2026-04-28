"""Trait system for PF2e Remaster action classification.

Traits classify actions into mechanical categories (MAP, flourish, open,
press) and immunity gates (mental, emotion, auditory, visual). The trait
registry is the single source of truth for which slugs belong to which
category.

(AoN: https://2e.aonprd.com/Traits.aspx)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TraitCategory(Enum):
    """Mechanical category a trait belongs to.

    MAP: contributes to multiple attack penalty (attack trait).
    FLOURISH: once-per-turn limit.
    OPEN: must be first attack-trait action of the turn.
    PRESS: requires a previous success this turn.
    IMMUNITY: gates action via target immunity_tags.
    DESCRIPTOR: flavor/subtype tag (e.g., fear is a descriptor of emotion).
        Does NOT gate immunity directly — immunity flows through the
        parent trait (emotion) instead.

    (AoN: https://2e.aonprd.com/Traits.aspx)
    """
    MAP = auto()
    FLOURISH = auto()
    OPEN = auto()
    PRESS = auto()
    IMMUNITY = auto()
    DESCRIPTOR = auto()


@dataclass(frozen=True)
class TraitDef:
    """Definition of a single trait slug.

    Attributes:
        slug: Lowercase trait name (e.g., "attack", "mental").
        category: Mechanical category this trait belongs to.
        immunity_tag: If non-empty, actions with this trait are blocked
            when the target has this tag in immunity_tags.
            Empty string for traits that don't gate immunity.
        aon_url: AoN reference URL.
    """
    slug: str
    category: TraitCategory
    immunity_tag: str
    aon_url: str


# -------------------------------------------------------------------------
# Trait Registry — 9 slugs for CP10.2
# -------------------------------------------------------------------------

TRAIT_REGISTRY: dict[str, TraitDef] = {
    "attack": TraitDef(
        slug="attack",
        category=TraitCategory.MAP,
        immunity_tag="",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=222",
    ),
    "flourish": TraitDef(
        slug="flourish",
        category=TraitCategory.FLOURISH,
        immunity_tag="",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=356",
    ),
    "open": TraitDef(
        slug="open",
        category=TraitCategory.OPEN,
        immunity_tag="",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=441",
    ),
    "press": TraitDef(
        slug="press",
        category=TraitCategory.PRESS,
        immunity_tag="",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=451",
    ),
    "mental": TraitDef(
        slug="mental",
        category=TraitCategory.IMMUNITY,
        immunity_tag="mental",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=424",
    ),
    "emotion": TraitDef(
        slug="emotion",
        category=TraitCategory.IMMUNITY,
        immunity_tag="emotion",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=311",
    ),
    # fear is a DESCRIPTOR — it does NOT have its own immunity_tag.
    # Fear immunity in PF2e flows through the emotion trait.
    # A creature immune to emotion effects is immune to fear effects,
    # but "immune to fear" is not a separate immunity gate.
    "fear": TraitDef(
        slug="fear",
        category=TraitCategory.DESCRIPTOR,
        immunity_tag="",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=345",
    ),
    "auditory": TraitDef(
        slug="auditory",
        category=TraitCategory.IMMUNITY,
        immunity_tag="auditory",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=227",
    ),
    "visual": TraitDef(
        slug="visual",
        category=TraitCategory.IMMUNITY,
        immunity_tag="visual",
        aon_url="https://2e.aonprd.com/Traits.aspx?ID=565",
    ),
}


# -------------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------------

def is_immune(
    action_traits: set[str] | frozenset[str],
    target_immunity_tags: set[str] | frozenset[str],
) -> bool:
    """Check if a target's immunity tags block an action's traits.

    For each known trait slug in action_traits, checks whether the trait's
    immunity_tag is present in target_immunity_tags. Unknown slugs (e.g.,
    weapon traits like "finesse", "agile", "reach") are silently skipped.

    Returns True if ANY action trait is blocked by target immunity.

    Args:
        action_traits: Set of trait slugs on the action.
        target_immunity_tags: Set of immunity tags on the target.

    Returns:
        True if the target is immune to this action.

    (AoN: https://2e.aonprd.com/Traits.aspx)
    """
    if not target_immunity_tags:
        return False
    for slug in action_traits:
        defn = TRAIT_REGISTRY.get(slug)
        if defn is None:
            continue  # unknown slug — silently skip
        if defn.immunity_tag and defn.immunity_tag in target_immunity_tags:
            return True
    return False


def has_trait(
    action_traits: set[str] | frozenset[str],
    category: TraitCategory,
) -> bool:
    """Check if any trait in action_traits belongs to the given category.

    Unknown slugs (not in TRAIT_REGISTRY) are silently skipped.

    Args:
        action_traits: Set of trait slugs on the action.
        category: The TraitCategory to check for.

    Returns:
        True if at least one known trait matches the category.

    (AoN: https://2e.aonprd.com/Traits.aspx)
    """
    for slug in action_traits:
        defn = TRAIT_REGISTRY.get(slug)
        if defn is None:
            continue  # unknown slug — silently skip
        if defn.category == category:
            return True
    return False
