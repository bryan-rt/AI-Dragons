# Characters

Canonical character data. Dual purpose:

1. **Current:** Storage for the party members' source-of-truth build data
2. **Future (Phase B):** Landing zone for Pathbuilder importer uploads

## Files

- `aetregan.json` — Pathbuilder JSON export for Aetregan (Bryan's Commander). **Canonical** — any discrepancy between this file and `sim/party.py::make_aetregan()` is a bug in code.
- `rook.json` — *Future.* Currently not provided; `sim/party.py::make_rook()` uses grounded defaults based on Automaton Guardian archetype.
- `dalai.json` — *Future.* Currently not provided; `sim/party.py::make_dalai()` uses grounded defaults based on Human Bard Warrior Muse archetype.
- `erisen.json` — *Future.* Currently not provided; `sim/party.py::make_erisen()` uses grounded defaults based on Elf Inventor Munitions Master archetype.

## Format

Pathbuilder JSON export format. Key fields: `build.name`, `build.class`, `build.level`, `build.ancestry`, `build.abilities`, `build.attributes` (ancestry HP, class HP, speed), `build.proficiencies` (numeric ranks), `build.feats`, `build.specials`, `build.weapons`, `build.armor`, `build.lores`.

## Reconciliation Process

When a new canonical JSON arrives (e.g., Rook's sheet eventually):

1. Compare against current grounded defaults in `sim/party.py`
2. File any discrepancies as a mini-checkpoint (follow CP4.5 pattern)
3. Update `make_X()` factory to match JSON exactly
4. Update `CHANGELOG.md` documenting the corrections
5. Ensure Strike Hard EV 8.55 regression still holds

## Phase B Preview

When the Pathbuilder importer ships (post-CP9, Phase B):

- Users upload their Pathbuilder JSON to this directory via a web interface
- Importer parses the JSON and produces a `Character` object
- Unknown feats are flagged with warnings but character is still usable
- Effects catalog (Phase B+) maps named feats to mechanical effects as it grows

At that point, `sim/party.py` becomes a fallback for test fixtures, and user-imported characters become the primary use case.
