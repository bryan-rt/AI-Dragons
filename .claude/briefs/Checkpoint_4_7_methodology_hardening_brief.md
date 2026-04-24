# Checkpoint 4.7: Methodology Hardening and CP4.6 Cleanup

## Context

CP4.6 restructuring succeeded but left three small bugs and a documentation gap. CP4.7 closes them.

The `CLAUDE.md` at the repo root has an excellent "Three-Pass Development System" section (you wrote it during CP4.6 — good work). The web-client counterpart `PROJECT_INSTRUCTIONS.md` in `.claude/project_reference/` has the old, shallower description. This checkpoint brings them into alignment and adds a named "Core Engineering Philosophy" section that both audiences read.

This is pure documentation/config work. **No production code changes. Test count stays at 255.**

## Scope

### What to do
1. Fix `characters/README.md` — wrong content currently lives there
2. Create `.claude/briefs/` directory with PLACEHOLDER.md
3. Update `.claude/context/current_state.md` for CP5.1 Pass 3a completion
4. Update `.claude/project_reference/ROADMAP.md` same
5. Update `PROJECT_INSTRUCTIONS.md` in `.claude/project_reference/` with:
   - New "Core Engineering Philosophy" section (evidence-first, test-first, logging-backed)
   - Structural three-pass methodology mirroring CLAUDE.md's
6. Add "Logging and Diagnostic Output" section to `.claude/context/conventions.md`
7. Fix test function name `test_warfare_lore_plus_8` → `test_warfare_lore_plus_7`
8. Commit with clear message

### What NOT to do
- No production code changes. `pf2e/`, `sim/`, `scenarios/` are untouched.
- No test behavior changes. The rename in step 7 is function-name only; the assertion stays `== 7`.
- No new Knowledge files. All new content lives in existing files.
- Don't delete the `.claude/prototype/` directory — those files are valuable history.

## Pre-implementation: read existing code

Call `view` on:
- `CLAUDE.md` (root) — read the "Three-Pass Development System" section; that's the template we're mirroring to PROJECT_INSTRUCTIONS.md
- `.claude/project_reference/PROJECT_INSTRUCTIONS.md` — what we're updating
- `.claude/context/conventions.md` — what we're extending
- `.claude/context/current_state.md` — what we're updating
- `.claude/project_reference/ROADMAP.md` — what we're updating
- `characters/README.md` — confirm the wrong-content bug
- `tests/test_skills.py` — find the function to rename

## Implementation Steps

### Step 1: Fix `characters/README.md`

The file currently contains the briefs archive README (starts with `# Briefs Archive`). Replace with this content:

```markdown
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
```

### Step 2: Create `.claude/briefs/` directory

```bash
mkdir -p .claude/briefs
```

Create `.claude/briefs/README.md` with this content:

```markdown
# Briefs Archive

Historical design and implementation briefs for every checkpoint. Reference these when working on a specific checkpoint or when needing context on past decisions.

## Naming convention

Briefs are named `checkpoint_<num>_pass_<num>_brief.md` where applicable:

- `pf2e_sim_task_brief_pass1.md` — initial project architecture
- `checkpoint_0_5_cleanup_brief.md` — CP0.5 corrections
- `checkpoint_1_pass_1_brief.md` through `checkpoint_4_pass_3_brief.md`
- `checkpoint_4_5_aetregan_reconciliation.md`
- `checkpoint_4_6_restructure_brief.md`
- `checkpoint_4_7_methodology_hardening_brief.md`
- `checkpoint_5_1_pass_1_brief.md`, `_pass_2_brief.md`, `_pass_3a_brief.md`

## Three-Pass Methodology

Each checkpoint follows a three-pass design before implementation:

**Pass 1 (Architecture):** High-level design, data model, algorithm choices, scope. No code. Ends with open questions for the user.

**Pass 2 (Refinements):** Incorporates feedback, resolves open questions, names defaults for undecided items. Still no code.

**Pass 3 (Implementation):** Step-by-step brief for the CLI agent. Specific file paths, code skeletons, tests, validation checklist, pitfalls.

For large checkpoints (CP5.1), Pass 3 splits into sub-briefs (3a, 3b, 3c).

## How to Use These Briefs

### When implementing a checkpoint
Read the Pass 3 brief for that checkpoint. Follow it exactly. Each brief specifies what to implement, what NOT to implement, files to read first, step-by-step order, tests to write, validation checklist, and pitfalls.

### When reviewing prior decisions
Read Pass 1 for architectural reasoning. Pass 2 for how decisions were refined based on feedback. Decision rationale often lives in Pass 1 and Pass 2, not just Pass 3.

### When flagging discrepancies
If implementation diverges from brief, reference the specific brief and step. Helps triage: is the brief wrong, or is the implementation wrong?

## Preserving History

All briefs stay in this directory indefinitely. When checkpoints are superseded, the historical brief remains. The CHANGELOG documents what shipped; the briefs document what was planned.
```

Create `.claude/briefs/PLACEHOLDER.md` with this content:

```markdown
# Briefs to be Added

This directory should contain all historical briefs. Bryan will copy the following files here from local storage:

- pf2e_sim_task_brief_pass1.md
- pf2e_sim_task_brief_pass1_5.md
- pf2e_sim_task_brief_pass2_5.md
- checkpoint_0_5_cleanup_brief.md
- checkpoint_1_pass_1_brief.md, checkpoint_1_pass_2_brief.md, checkpoint_1_pass_3_brief.md
- checkpoint_2_pass_1_brief.md, checkpoint_2_pass_2_brief.md, checkpoint_2_pass_3_brief.md
- checkpoint_3_pass_1_brief.md, checkpoint_3_pass_2_brief.md, checkpoint_3_pass_3_brief.md
- checkpoint_4_pass_1_brief.md, checkpoint_4_pass_2_brief.md, checkpoint_4_pass_3_brief.md
- checkpoint_4_5_aetregan_reconciliation.md
- checkpoint_4_6_restructure_brief.md
- checkpoint_4_7_methodology_hardening_brief.md (this brief)
- checkpoint_5_1_pass_1_brief.md
- checkpoint_5_1_pass_2_brief.md
- checkpoint_5_1_pass_3a_brief.md

Not all may be present locally — that's fine. Copy what you have.

Delete this PLACEHOLDER.md file once the briefs have been added.
```

### Step 3: Update `.claude/context/current_state.md`

Replace the entire file with:

```markdown
# Current State

**Last updated:** After CP5.1 Pass 3a implementation and CP4.7 methodology hardening.

Update this file at the end of every checkpoint.

## Latest Test Count

**255 passing** (after CP5.1 Pass 3a).

## Active Work

**CP5.1 Pass 3b — Algorithms** (pending brief).

Expected scope (from Pass 2 architectural commitments):
- `sim/round_state.py`: `RoundState` with shallow-clone + frozenset conditions
- `sim/search.py`: beam search K=50/20/10 at depth 3
- Adversarial enemy sub-search (K=20, depth 3)
- Hybrid state threading: EV-collapse with kill/drop branching at 5% threshold
- Scoring function: `kill_value = max_hp + 10 × num_attacks`, `drop_cost = max_hp + 10 × role_multiplier` (Dalai = 2x)
- `sim/initiative.py`: seeded Perception + d20 rolling
- `pf2e/damage_pipeline.py`: strict PF2e damage resolution (attack → damage → Intercept → Shield Block → resistance → temp HP)

Expected test count after Pass 3b: ~295-315.

## Known Regression Anchors

All must pass at every checkpoint:

- **EV 8.55** — Rook longsword reaction Strike with Anthem vs Bandit1 AC 15 (Strike Hard tactic). Located in `tests/test_scenario.py::TestKillerValidation::test_strike_hard_from_disk`.
- **55% prone probability** — Tactical Takedown vs Reflex +5 DC 17. `tests/test_tactics.py`.
- **EV 5.95 per target** — Light mortar 2d6 DC 17 vs Reflex +5. `tests/test_combat_math.py`.
- **Aetregan max HP 15** — After CP4.5. `tests/test_hp.py`.
- **Aetregan Warfare/Deity Lore +7** — Int +4 + trained +3 = +7 at level 1. `tests/test_skills.py`.

## Completed Checkpoints Summary

| CP | Test Count | Key Addition |
|---|---|---|
| CP0 | ~40 | Foundation types |
| CP0.5 | 97 | Corrections and cleanup |
| CP1 | 123 | Tactic dispatcher |
| CP2 | 171 | Grid and spatial |
| CP3 | 181 | Scenario loading |
| CP4 | 199 | Defensive value |
| CP4.5 | 207 | Aetregan reconciliation |
| CP5.1 Pass 3a | 255 | Foundation (data model, skill system, HP tracking, initiative parsing) |
| CP4.6 | 255 | Repo restructuring (no code changes) |
| CP4.7 | 255 | Methodology documentation (no code changes) |

## Next Up

Write CP5.1 Pass 3b brief, then implement.

## Known TODOs

From past checkpoints, things flagged for future resolution:

- **CP5.1 3b:** Support-role multiplier hardcoded to Dalai by name. Refactor to `role_weight` field on Character in CP6.
- **CP5.1 3b:** Reaction policies (Intercept, Shield Block) use greedy heuristics. Optimal reaction timing deferred to CP6.
- **CP5.2:** Multi-enemy coordination (flanking, spread damage) emerges from single-best-response sometimes but isn't explicitly modeled. CP6 upgrade candidate.
- **CP6:** Expectimax enemy search over top-3 enemy plans (currently single-best-response).
- **CP6:** Scoring weight calibration from CP7 feedback.
- **CP8:** Level 2+ character advancement. Aetregan's L2 Plant Banner upgrade is on this.
- **Phase B (post-CP9):** Pathbuilder importer, effects catalog extraction from hard-coded flags.

## Links

- Repo: https://github.com/bryan-rt/AI-Dragons
- AoN (PF2e rules reference): https://2e.aonprd.com
```

### Step 4: Update `.claude/project_reference/ROADMAP.md`

Find the section `## In Progress` and replace the entire CP5.1 Pass 3a block. Specifically, change the status line at the top from:

```
Status at time of last update: CP5.1 Pass 3a implementation delivered to CLI agent, awaiting completion and review.
```

to:

```
Status at time of last update: CP5.1 Pass 3a complete (255 tests). CP4.6 and CP4.7 restructuring/methodology work complete. CP5.1 Pass 3b pending brief.
```

Then find the `### CP5.1 Pass 3a — Foundation (active)` heading under `## In Progress` and move that section into `## Completed Checkpoints` (at the bottom, after CP4.5). Rename the heading to `### CP5.1 Pass 3a — Foundation`. Delete the "(active)" marker. Update the opening to note it shipped 255 tests.

Also, add these two entries to the completed list:

```markdown
### CP4.6 — Repo Restructuring
255 tests preserved (no code changes).
- `CLAUDE.md` at repo root for CLI agent context
- `.claude/context/` for agent-facing reference docs
- `.claude/project_reference/` as version-controlled mirror of Claude Project knowledge
- `.claude/briefs/` scaffolding for historical brief archive
- `characters/` directory with aetregan.json canonical data
- Removed `project_restructure_docs/` staging directory

### CP4.7 — Methodology Hardening
255 tests preserved (no code changes).
- Fixed `characters/README.md` content bug from CP4.6
- Populated `.claude/briefs/` scaffolding
- Added "Core Engineering Philosophy" section to `PROJECT_INSTRUCTIONS.md`
- Structural three-pass methodology in `PROJECT_INSTRUCTIONS.md` mirrors the one in `CLAUDE.md`
- Logging and diagnostic output conventions added to `conventions.md`
```

The rest of the ROADMAP (Pending Checkpoints section) stays as-is.

### Step 5: Update `PROJECT_INSTRUCTIONS.md`

Location: `.claude/project_reference/PROJECT_INSTRUCTIONS.md`.

**5a.** Find this section:

```markdown
## Three-Pass Methodology

Every checkpoint goes through three passes before implementation:
[...]
```

Replace the entire "Three-Pass Methodology" section (everything from that heading down through and including the line `**All briefs are saved to `.claude/briefs/` in the repo** for historical reference.`) with:

```markdown
## Core Engineering Philosophy

Three principles govern every checkpoint on this project. Name them, honor them, and flag when they're being violated.

### 1. Evidence-first. Never code from assumptions.

Every PF2e rule cited in a brief must link to https://2e.aonprd.com. Every mechanical claim must be verifiable. When uncertain, web_search AoN — don't trust memory. When you don't know, flag it as `(UNVERIFIED — please check)` rather than guessing.

This principle has caught multiple real errors:
- **Aetregan Wis 11 → 12** (CP0.5) — boost arithmetic assumed incorrectly
- **Mortar EV 5.60 → 5.95** (CP0.5) — save boundary rule applied incorrectly
- **Banner aura 30 → 40 ft** (CP4) — Plant Banner expansion missed
- **Scorpion Whip vs Whip** (CP4.5) — weapon trait assumed from name similarity
- **Commander Perception trained → expert** (CP4.5) — class feature progression assumed

Every one of these was caught in a brief-writing pass *before* code was written. The three-pass methodology exists to preserve this gap.

### 2. Test-first. Tests ratchet forward.

Every checkpoint adds tests that lock in its correctness. The regression chain (EV 8.55 at every checkpoint since CP1, 55% prone probability, 5.95 mortar EV, HP targets) is the project's backbone. When a test breaks, investigate before editing the test's expected value — the code is usually wrong, not the test.

Every new function in a brief needs tests: happy path, edge cases, error cases. Every correction to a rule becomes a regression test so the error doesn't silently return.

### 3. Logging-backed. Complex algorithms need diagnostic output.

When CP5.1 Pass 3b+ introduces search and state threading, eyeballing EVs won't scale. Briefs will specify logging (beam state per depth, pruned branches, scoring breakdowns) and CLI flags for diagnostic output. Don't skip this — the alternative is debugging by hypothesis, which burns cycles.

Complex-algorithm briefs must specify what logging to emit. Simple rule-derivation briefs may skip this.

## Three-Pass Methodology

Every checkpoint passes through three structured phases before code ships. Each pass has a distinct deliverable. Don't skip passes or combine them without explicit authorization.

### Pass 1 — High-Level Planning

**Input:** A Pass 1 brief describing the problem, scope, and design questions.

**Your job:**
1. Read the brief, referenced code files, and relevant `.claude/context/` docs
2. Research PF2e rules on Archives of Nethys — verify every mechanical claim
3. Enter planning mode. Do NOT write code.
4. Produce a high-level architectural plan: data model, module structure, function signatures, integration points, test strategy
5. Surface concerns, ambiguities, and open questions that need user input before committing to a design
6. Mark unverifiable claims as `(UNVERIFIED — please check)`

**Deliverable:** A markdown plan document. No code.

### Pass 2 — Refinement

**Input:** A Pass 2 brief with corrections, clarifications, and decisions on the open questions from Pass 1.

**Your job:**
1. Apply each correction to the plan
2. Finalize any remaining design decisions
3. Produce a refined plan with concrete data: exact field names, exact function signatures, exact test expectations, exact AoN URLs
4. Flag remaining blockers for Pass 3

**Deliverable:** A compact updated plan. Still no code.

### Pass 3 — Implementation

**Input:** A Pass 3 brief with step-by-step implementation instructions, code skeletons, test specifications, and a validation checklist.

**Your job:**
1. Read the brief end-to-end before starting
2. Read the files listed in "Pre-implementation: read existing code"
3. Follow the implementation steps in order
4. Write the tests specified in the brief
5. Run `pytest tests/ -v` — all tests must pass
6. Verify the killer regression (EV 8.55 from disk) still holds
7. Update CHANGELOG.md with the brief's CHANGELOG section
8. Update `.claude/context/current_state.md` with new test count and status
9. Commit with a clear checkpoint message

**Deliverable:** Working code with passing tests, committed and pushed.

### Why Three Passes?

Pass 1 catches design errors before code is written. Pass 2 catches rule errors before implementation commits. Pass 3 executes a validated plan. This system has caught every major rule mistake on the project. Don't collapse passes to save time — you'll spend it later on rework.

For large checkpoints (CP5.1), Pass 3 itself splits into sub-phases (3a, 3b, 3c), each with its own brief-review-implement cycle. The three-pass structure still applies to the checkpoint as a whole.

**All briefs are saved to `.claude/briefs/` in the repo** for historical reference.
```

**5b.** Find the line near the top that reads:

```
**Test count at last checkpoint:** 207
```

Change it to:

```
**Test count at last checkpoint:** 255 (after CP5.1 Pass 3a)
```

### Step 6: Update `.claude/context/conventions.md`

Append a new section at the end of the file:

```markdown

## Logging and Diagnostic Output

For simple rule-derivation code (combat math, equipment, character builders), tests provide enough visibility. Don't add logging.

For complex algorithms (search, state threading, multi-step evaluators), logging is essential for debugging. When a brief introduces algorithmic work, it will specify logging requirements. Follow them:

- **Use the standard library `logging` module.** No print statements in production code. Tests may use print for debug output during development but should be cleaned before committing.
- **Logger per module:** `logger = logging.getLogger(__name__)` at module top. Propagates to the root logger; user controls verbosity.
- **Log levels:**
  - `DEBUG`: per-iteration detail (beam state per depth, each candidate evaluated, scoring breakdowns)
  - `INFO`: checkpoint-level events (round start, action chosen, EV of final plan)
  - `WARNING`: recoverable anomalies (probability sum drift, unexpected empty result)
  - `ERROR`: genuine bugs that should not happen in validated code
- **CLI flags for diagnostic output.** Algorithm-heavy modules expose `--debug-search` or similar flags that set logger levels at runtime. The flag is documented in the brief that introduces it.
- **Logged data is structured.** Prefer f-string formatting of specific fields over dumping whole objects. `logger.debug(f"Beam depth {d}: {len(beam)} candidates, best EV {best:.2f}")` — not `logger.debug(f"Beam: {beam}")`.
- **Tests may assert on log output** for critical paths. Use `caplog` fixture in pytest when verifying that warnings fire when expected.

## Diagnostic Conventions for Complex Algorithm Work

When reviewing output from complex algorithms during development:

- Dump full state at a specific depth or iteration with a CLI flag, not by editing the code
- Probability sums should be verified with `ActionResult.verify_probability_sum()` in any test that constructs action results
- When EVs don't match expectations, log the inputs (bonuses, DCs, outcome counts) before changing anything — the bug is usually upstream of where you first noticed it
- Keep a "killer regression" test at every checkpoint. Small regressions in beam search can shift EVs by fractions; the killer test is your canary
```

### Step 7: Fix test function name

In `tests/test_skills.py`, find:

```python
def test_warfare_lore_plus_8(self) -> None:
```

Rename to:

```python
def test_warfare_lore_plus_7(self) -> None:
```

Also fix the docstring inside that function — it's currently confused about the math. Replace the docstring with:

```python
    """Warfare Lore: Int 18 (+4) + trained (+3 at L1) = +7.
    
    Trained proficiency at level 1 = rank.value (2) + level (1) = 3.
    Plus Int mod +4 = total +7.
    """
```

Do the same for `test_deity_lore_plus_7` — the assertion is already correct, but verify the name matches and the docstring is clean.

Run `pytest tests/test_skills.py -v` to confirm the rename didn't break anything.

### Step 8: Commit

```bash
git add -A
git commit -m "CP4.7: Methodology hardening and CP4.6 cleanup

- Fix characters/README.md wrong-content bug from CP4.6
- Create .claude/briefs/ scaffolding with README and PLACEHOLDER
- Update .claude/context/current_state.md: 207 -> 255 tests, Pass 3a complete
- Update .claude/project_reference/ROADMAP.md with CP5.1 3a, CP4.6, CP4.7 entries
- Add 'Core Engineering Philosophy' section to PROJECT_INSTRUCTIONS.md naming
  evidence-first, test-first, and logging-backed as core principles
- Replace 'Three-Pass Methodology' section in PROJECT_INSTRUCTIONS.md with
  structural template mirroring CLAUDE.md
- Add 'Logging and Diagnostic Output' section to conventions.md
- Rename test_warfare_lore_plus_8 -> test_warfare_lore_plus_7 (assertion was
  already correct at 7; only the function name said 8)

No production code changes. Test count remains 255."
```

Push to GitHub.

## Validation checklist

- [ ] `characters/README.md` describes the characters directory, not briefs
- [ ] `.claude/briefs/README.md` exists with briefs archive content
- [ ] `.claude/briefs/PLACEHOLDER.md` exists
- [ ] `.claude/context/current_state.md` shows 255 tests, Pass 3a complete
- [ ] `.claude/project_reference/ROADMAP.md` lists CP5.1 Pass 3a, CP4.6, and CP4.7 as complete
- [ ] `PROJECT_INSTRUCTIONS.md` has "Core Engineering Philosophy" section naming evidence-first, test-first, logging-backed
- [ ] `PROJECT_INSTRUCTIONS.md` has structural three-pass methodology (Pass 1/2/3 with "Your job:" deliverables) matching CLAUDE.md
- [ ] `conventions.md` ends with "Logging and Diagnostic Output" section
- [ ] `test_warfare_lore_plus_7` exists; `test_warfare_lore_plus_8` does not
- [ ] `pytest tests/ -v` shows **255 passed** — no regression
- [ ] Commit pushed to GitHub

## Common pitfalls

- **Don't accidentally delete the `.claude/prototype/` directory.** It's valuable history. Only touch files this brief names.
- **Don't edit `CLAUDE.md`.** It's already in the right shape. `PROJECT_INSTRUCTIONS.md` is what needs to catch up.
- **Don't change any assertion values in tests.** The rename in Step 7 is function-name only.
- **Verify the markdown in PROJECT_INSTRUCTIONS.md doesn't accidentally break the file.** Render the file (or at minimum re-read the "Core Engineering Philosophy" section) after editing to confirm the heading levels and list formatting are intact.
- **Bryan's historical briefs are still missing from `.claude/briefs/`.** That's fine — Step 2 creates PLACEHOLDER.md for Bryan to follow up on manually. Don't try to fabricate the briefs yourself.

## What comes after

Bryan will re-upload the updated `PROJECT_INSTRUCTIONS.md` to the Claude Project's Instructions field (paste), and re-upload `ROADMAP.md` to Knowledge. Then he'll start a new Claude conversation in the Project, paste the kickoff message, and review CP5.1 Pass 3a implementation in that new context before writing Pass 3b.