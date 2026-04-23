"""Test fixtures — re-exports the canonical party from sim/party.py.

Historical location for factories; production code now lives in
sim/party.py. Tests import from here for backward compatibility.
"""

from sim.party import (  # noqa: F401
    DAGGER,
    FULL_PLATE,
    JAVELIN,
    LEATHER_ARMOR,
    LONGSWORD,
    RAPIER,
    SCORPION_WHIP,
    STEEL_SHIELD,
    STUDDED_LEATHER,
    SUBTERFUGE_SUIT,
    WHIP,
    make_aetregan,
    make_dalai,
    make_erisen,
    make_rook,
    make_rook_combat_state,
)
