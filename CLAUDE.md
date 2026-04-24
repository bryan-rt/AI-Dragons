# CLAUDE.md — CLI Agent Context

You are working on a Pathfinder 2e Remaster tactical combat simulator. This document is loaded automatically when you start work in this repo.

## Quick Context

- **Language:** Python 3.10+
- **Dependencies:** Standard library only, plus pytest for tests
- **Run tests:** `pytest tests/ -v` from repo root
- **Current test count:** See `.claude/context/current_state.md` for latest
- **Main branches:** `main` (only branch); work directly on it

## What to Read First

Before making any changes, read these files in order:

1. **This file (`CLAUDE.md`)** — you're already reading it
2. **`.claude/context/current_state.md`** — current checkpoint, test count, active work
3. **`.claude/context/conventions.md`** — code conventions
4. **`.claude/context/architecture.md`** — module layout and layering rules
5. **`.claude/context/pitfalls.md`** — gotchas accumulated from past checkpoints

If working on a specific brief:
- **`.claude/briefs/`** contains all briefs delivered so far
- Find the relevant Pass 3 brief (e.g., `checkpoint_5_1_pass_3a_brief.md`)
- Follow the brief's implementation steps and validation checklist exactly

## Standing Rules

1. **Verify against AoN.** Any PF2e rule you implement must link to https://2e.aonprd.com. Use web_fetch or web_search to verify when uncertain.

2. **Read existing code before editing.** Use `view` to understand structure before making changes. The briefs specify which files to read.

3. **Tests mirror production.** Test file `test_X.py` tests module `X.py`. Add tests to existing test files where appropriate; create new ones as briefs specify.

4. **Follow the brief exactly.** If a brief says "15 action types," don't add a 16th. If it says "defer to CP5.2," don't implement it now. Scope discipline is essential.

5. **Standard library only.** No third-party dependencies in production code (pytest in tests is fine).

6. **Docstrings cite AoN URLs.** Every non-obvious rule gets a URL in the function docstring or inline comment.

7. **No circular imports.** `pf2e/` does not import from `sim/`. Ever.

8. **Commit after passing tests.** Don't commit broken code. Run `pytest tests/ -v` before every commit.

## Project Structure

```
pf2e/              # Pure rules engine
  types.py         # Enums (Ability, ProficiencyRank, WeaponCategory, Skill, etc.)
  abilities.py     # AbilityScores
  proficiency.py   # proficiency_bonus()
  equipment.py     # Weapon, ArmorData, Shield
  character.py     # Character, CombatantState, EnemyState
  combat_math.py   # All derivation functions
  tactics.py       # Tactic system + evaluators
  actions.py       # (CP5.1+) Action types and dataclasses
  damage_pipeline.py # (CP5.1+) Damage resolution

sim/               # Simulator layer (uses pf2e/)
  grid.py          # Grid geometry, parsing, BFS
  grid_spatial.py  # GridSpatialQueries
  party.py         # Character factories for the canonical party
  scenario.py      # Scenario file loading

scenarios/         # .scenario files (text format)
characters/        # Character JSON files (for Phase B importer)
tests/             # Tests mirror production structure
.claude/           # Claude context and brief history
```

See `.claude/context/architecture.md` for the full module layout and layering rules.

## Three-Pass Development System

Every checkpoint follows a three-pass loop. Each pass has a distinct purpose and deliverable. Do not skip passes or combine them without explicit authorization.

### Pass 1 — High-Level Planning

**Input:** A Pass 1 brief describing the problem, scope, and design questions.

**Your job:**
1. Read the brief, all referenced code files, and relevant `.claude/context/` docs
2. Research PF2e rules on Archives of Nethys (web_fetch/web_search) — verify every mechanical claim
3. Enter planning mode. Do NOT write code.
4. Produce a high-level architectural plan covering: data model, module structure, function signatures, integration points, test strategy
5. Surface concerns, ambiguities, and open questions that need user input before committing to a design
6. Mark anything you cannot verify as `(UNVERIFIED — please check)`

**Deliverable:** A markdown plan document. No code.

### Pass 2 — Refinement

**Input:** A Pass 2 brief with corrections, clarifications, and decisions on the open questions from Pass 1.

**Your job:**
1. Apply each correction to the plan
2. Finalize any remaining design decisions
3. Produce a refined plan with concrete data: exact field names, exact function signatures, exact test expectations, exact AoN URLs
4. Flag any remaining blockers for Pass 3

**Deliverable:** A compact updated plan. Still no code.

### Pass 3 — Implementation

**Input:** A Pass 3 brief with step-by-step implementation instructions, exact code skeletons, test specifications, and a validation checklist.

**Your job:**
1. Read the brief end-to-end before starting
2. Read the files listed in "Pre-implementation: read existing code"
3. Follow the implementation steps in order
4. Write the tests specified in the brief
5. Run `pytest tests/ -v` — all tests must pass
6. Verify the killer regression: Strike Hard EV 8.55 from disk must still hold
7. Update `CHANGELOG.md` with the brief's CHANGELOG section
8. Update `.claude/context/current_state.md` with new test count and status
9. Commit with a clear message referencing the checkpoint (e.g., "CP5.1 Pass 3a: foundation implementation")
10. Push to GitHub

**Deliverable:** Working code with passing tests, committed and pushed.

### Why Three Passes?

Pass 1 catches design errors before code is written. Pass 2 catches rule errors before implementation commits. Pass 3 executes a validated plan. This system has caught multiple PF2e rule mistakes (mortar EV, banner aura expansion, Aetregan's stats) that would have been expensive to fix after implementation.

## If You Find Discrepancies

If something in a brief conflicts with verified PF2e rules, or existing code behaves differently than expected, **stop and flag it** rather than guessing. The user can clarify. This has happened several times (Wis 11→12 correction, mortar EV 5.95 vs 5.60, banner aura expansion) and catching it early is always better than implementing wrong code.

## Killer Regression Test

The single most important test is in `tests/test_scenario.py::TestKillerValidation::test_strike_hard_from_disk`. It verifies that loading the canonical scenario and evaluating Strike Hard produces EV 8.55. This test must pass after every checkpoint. If you break it, fix before moving on.

## Key Numbers to Remember

- **EV 8.55** — Strike Hard with Anthem (regression anchor)
- **Aetregan:** Cha 10, Perception expert, Scorpion Whip, ancestry_hp 6, class_hp 8, max HP 15
- **Rook:** Automaton Guardian, max HP 23, guardian_reactions 1
- **Dalai:** Human Bard, max HP 17, Cha 18
- **Erisen:** Elf Inventor, max HP 16, Speed 35

## `/brief` Command

When the user types `/brief` followed by the brief content (pasted inline), do the following:

### Step 1: Save the brief

1. Extract the checkpoint name from the brief's title/header (e.g., "Checkpoint 5.1 Pass 3b" → `checkpoint_5_1_pass_3b_brief.md`)
2. Write the full pasted content to `.claude/briefs/<extracted_name>.md`
3. Confirm the file was saved

### Step 2: Determine the pass type

Identify which pass it is from the brief content:
- **Pass 1**: Title/header contains "Pass 1", "Architectural Plan", or "Planning". The brief asks for a plan, not code.
- **Pass 2**: Title/header contains "Pass 2", "Corrections", or "Refinement". The brief provides corrections to a prior plan.
- **Pass 3**: Title/header contains "Pass 3", "Implementation", or "Execution". The brief provides step-by-step implementation instructions.

### Step 3: Execute the brief

**Pass 1 — Planning:**
1. Read the brief end-to-end
2. Read all files listed in the brief's "read existing code" or "pre-implementation" section
3. Read `.claude/context/current_state.md`, `.claude/context/architecture.md`, and `.claude/context/pitfalls.md`
4. Research any PF2e rules mentioned using web search/fetch against Archives of Nethys (https://2e.aonprd.com/)
5. Enter planning mode — do NOT write code
6. Produce the architectural plan **as chat output** (not saved to a file)
7. Surface concerns, ambiguities, open questions, and anything marked UNVERIFIED
8. End with a summary table of key decisions and any UNVERIFIED tags
9. **Do NOT save the plan to a file.** The user will relay it to the web client for review. Only the brief itself gets saved (Step 1).

**Pass 2 — Refinement:**
1. Read the brief end-to-end
2. Apply each correction listed in the brief to the prior plan
3. Research any new AoN citations needed
4. Finalize design decisions with concrete field names, signatures, and test expectations
5. Flag any remaining blockers
6. Output the refined plan **as chat output** (not saved to a file)
7. **Do NOT save the plan to a file.** Same as Pass 1 — user relays to web client.

**Pass 3 — Implementation:**
1. Read the brief end-to-end before writing any code
2. Read every file listed in "Pre-implementation: read existing code"
3. Follow the implementation steps in the exact order given
4. Write tests as specified
5. Run `pytest tests/ -v` — all tests must pass
6. Verify the killer regression (Strike Hard EV 8.55) still holds
7. Update `CHANGELOG.md`
8. Commit with a clear checkpoint message
9. Push to GitHub

### What gets saved vs what gets output

- **Briefs** (from user): always saved to `.claude/briefs/` as `.md` files (Step 1)
- **Plans** (Pass 1/2 output): output as chat text only — NOT saved to files. The user copies them to the web client for review.
- **Code** (Pass 3 output): saved to production files, tested, committed, pushed

### Example usage

```
/brief
# Checkpoint 5.1.3b Pass 1: Algorithms — Architectural Plan

## Context
...the full brief content pasted here...
```

This saves the brief to `.claude/briefs/checkpoint_5_1_3b_pass_1_brief.md`, identifies it as Pass 1, reads context files, researches AoN, and outputs the plan as chat text with a summary table.

## Contact

The project owner is Bryan (GitHub: bryan-rt). Main work happens in Claude conversations (strategic planning) and CLI agent sessions (implementation). The repo is public at https://github.com/bryan-rt/AI-Dragons.
