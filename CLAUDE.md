# CLAUDE.md — CLI Agent Context

You are working on a Pathfinder 2e Remaster tactical combat simulator. This document is loaded automatically when you start work in this repo.

## Quick Context

- **Language:** Python 3.10+
- **Dependencies:** Standard library only, plus pytest for tests
- **Run tests:** `pytest tests/ -v` from repo root
- **Current test count:** See `.claude/context/current_state.md` for latest (578 as of CP7.2)
- **Main branches:** `main` (only branch); work directly on it

## What to Read First

Before making any changes, read these files in order:

1. **This file (`CLAUDE.md`)** — you're already reading it
2. **`.claude/context/current_state.md`** — current checkpoint, test count, active work
3. **`.claude/context/conventions.md`** — code conventions
4. **`.claude/context/architecture.md`** — module layout and layering rules
5. **`.claude/context/pitfalls.md`** — gotchas accumulated from past checkpoints
6. **`.claude/context/cp10_architecture.md`** — full CP10 layer map and specs (if working on CP10)

If working on a specific brief:
- **`.claude/briefs/`** contains all briefs delivered so far
- Find the relevant Pass 3 brief and follow it exactly

## Standing Rules

1. **Verify against AoN.** Any PF2e rule you implement must link to https://2e.aonprd.com. Use web_fetch or web_search to verify when uncertain.

2. **Read existing code before editing.** Use `view` to understand structure before making changes. The briefs specify which files to read.

3. **Tests mirror production.** Test file `test_X.py` tests module `X.py`. Add tests to existing test files where appropriate; create new ones as briefs specify.

4. **Follow the brief exactly.** Scope discipline is essential. If a brief says "15 action types," don't add a 16th. If it says "defer to CP10.2," don't implement it now.

5. **Standard library only.** No third-party dependencies in production code (pytest in tests is fine).

6. **Docstrings cite AoN URLs.** Every non-obvious rule gets a URL in the function docstring or inline comment.

7. **No circular imports.** `pf2e/` does not import from `sim/`. Ever.

8. **Commit after passing tests.** Run `pytest tests/ -v` before every commit. Don't commit broken code.

## Project Structure

```
pf2e/              # Pure rules engine
  types.py         # Enums (Ability, ProficiencyRank, WeaponCategory, Skill, etc.)
  abilities.py     # AbilityScores
  proficiency.py   # proficiency_bonus()
  equipment.py     # Weapon, ArmorData, Shield
  character.py     # Character, CombatantState, EnemyState
  combat_math.py   # All derivation functions + D20Outcomes + enumerate_d20_outcomes
  tactics.py       # Tactic system + evaluators
  actions.py       # ActionType enum + all current action evaluators
  spells.py        # SpellDefinition, SpellPattern, SPELL_REGISTRY
  damage_pipeline.py # Damage resolution (Intercept → Shield Block → Resistance → Temp → HP)
  effects/         # Placeholder — handler registry deferred (D30)

sim/               # Simulator layer (uses pf2e/)
  grid.py          # Grid geometry, parsing, BFS
  grid_spatial.py  # GridSpatialQueries
  party.py         # Character factories (delegate to Foundry importer)
  scenario.py      # Scenario file loading
  round_state.py   # CombatantSnapshot, EnemySnapshot, RoundState
  search.py        # Beam search K=50/20/10, adversarial sub-search, scoring
  candidates.py    # generate_candidates()
  solver.py        # Full combat solver (solve_combat, CombatSolution)
  initiative.py    # roll_initiative()
  cli.py           # CLI entry point
  catalog/         # Rule Element session cache (Phase B+)
  importers/
    foundry.py     # Foundry VTT actor JSON importer

scenarios/         # .scenario files (text format)
characters/        # fvtt-*.json (Foundry actor exports — authoritative)
tests/             # Tests mirror production structure
.claude/           # Claude context and brief history
  context/         # current_state.md, architecture.md, conventions.md, pitfalls.md, cp10_architecture.md
  briefs/          # All historical briefs
```

See `.claude/context/architecture.md` for the full module layout and layering rules.
See `.claude/context/cp10_architecture.md` for the CP10 nine-layer rebuild plan.

## Three-Pass Development System

Every checkpoint follows a three-pass loop. Each pass has a distinct purpose and deliverable. Do not skip passes or combine them without explicit authorization.

### Pass 1 — High-Level Planning
Read brief + existing code + AoN rules. Produce architectural plan. Surface concerns and open questions. No code.

### Pass 2 — Refinement
Apply corrections. Finalize design with exact field names, signatures, test expectations, AoN URLs. Still no code.

### Pass 3 — Implementation
Read brief end-to-end. Read existing code. Follow implementation steps in order. Write tests. Run `pytest tests/ -v`. Verify killer regression. Update CHANGELOG.md. Update `current_state.md`. Commit and push.

### What gets saved vs what gets output

- **Briefs** (from user via `/brief`): always saved to `.claude/briefs/` as `.md` files
- **Plans** (Pass 1/2 output): output as chat text only — NOT saved to files
- **Code** (Pass 3 output): saved to production files, tested, committed, pushed

## If You Find Discrepancies

If something in a brief conflicts with verified PF2e rules, or existing code behaves differently than expected, **stop and flag it** rather than guessing. The user can clarify. This system has caught multiple mistakes (Wis 11→12, mortar EV 5.95 vs 5.60, banner aura expansion, Rook weapon correction) and catching them early is always better than implementing wrong code.

## Killer Regression Test

The killer regression test verifies EV 7.65 for the Strike Hard scenario. This must pass after every checkpoint. If it breaks, fix before moving on.

**Note:** EV was 8.55 through CP7.1. Changed to 7.65 in Phase B when the Foundry importer correctly identified Rook's primary weapon as Earthbreaker (d6) not Longsword (d8).

## Key Numbers to Remember

- **EV 7.65** — Strike Hard with Anthem and Rook Earthbreaker (regression anchor, 23rd verification)
- **EV was 8.55** before Phase B — if you see old briefs referencing 8.55, that was correct at the time
- **Aetregan:** WIS 10, CHA 12 (from Foundry JSON), Scorpion Whip, ancestry_hp 6, class_hp 8, max HP 15
- **Rook:** Automaton Guardian, max HP 23, primary weapon Earthbreaker d6, immune to mental/emotion
- **Dalai:** Human Bard, max HP 17, Cha 18, Rapier Pistol
- **Erisen:** Elf Inventor, max HP 16, Speed 35, Dueling Pistol

## Current Active Work: CP10

CP10 is a nine-layer architectural rebuild. The next checkpoint is CP10.1 (Roll Foundation).

CP10.1 creates `pf2e/rolls.py` with:
- `RollType` enum: `STANDARD | FLAT`
- `FortuneState` enum: `NORMAL | FORTUNE | MISFORTUNE | CANCELLED`
- `flat_check(dc: int) -> float` — P(d20 ≥ dc), no modifiers, clamped [0.0, 1.0]
- `FortuneState.combine(has_fortune, has_misfortune)` helper

CP10.1 is **purely additive** — no existing file changes. Only two new files.

See `.claude/context/cp10_architecture.md` for the full specification.

## `/brief` Command

When the user types `/brief` followed by the brief content:

1. Save the brief to `.claude/briefs/<checkpoint_name>.md`
2. Identify the pass type (Pass 1 = plan, Pass 2 = refine, Pass 3 = implement)
3. Execute accordingly:
   - **Pass 1/2:** Read brief + context + AoN. Output plan as chat text only (not saved to file).
   - **Pass 3:** Read brief + existing code. Implement. Test. Commit. Push.

## Contact

The project owner is Bryan (GitHub: bryan-rt). Main work happens in Claude conversations (strategic planning) and CLI agent sessions (implementation). The repo is public at https://github.com/bryan-rt/AI-Dragons.
