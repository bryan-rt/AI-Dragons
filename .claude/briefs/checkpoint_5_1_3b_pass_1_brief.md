# Checkpoint 5.1.3b Pass 1: Algorithms — Architectural Plan

## Meta

- **Checkpoint:** CP5.1.3b (was "CP5.1 Pass 3b — Algorithms" under the old naming)
- **Pass:** 1 (architectural planning — **no code**)
- **Predecessor:** CP5.1.3a (foundation data model, 255 tests, shipped)
- **Successor:** CP5.1.3c (action evaluators)
- **Expected Pass 3 test count:** 295-315 (~40-60 new tests)

### Naming convention note

This brief introduces a cleaner checkpoint naming scheme:
- **CP5.1.3b** replaces "CP5.1 Pass 3b" as the checkpoint name
- **CP5.1.3b Pass 1/2/3** are this checkpoint's three-pass loop
- **CP5.1.3c** will be the next checkpoint (action evaluators)

Save this brief as `.claude/briefs/checkpoint_5_1_3b_pass_1_brief.md`.

Do **not** rename existing briefs in `.claude/briefs/` — they stay under their historical names. New briefs use the new convention. The Pass 3 brief for this checkpoint will include a docs-update step to propagate the new naming to `ROADMAP.md`, `.claude/context/current_state.md`, `DECISIONS.md`, and `CHANGELOG.md`.

## Your deliverable for this pass

A markdown planning document saved to `.claude/briefs/checkpoint_5_1_3b_pass_1_plan.md`. **No production code changes. No test changes.** The plan is what I review before we commit to Pass 2.

The plan must cover every section listed under "Plan contents" below. Where I've flagged design questions, produce a recommendation with reasoning, not just a restatement of the question. Mark any claim you cannot verify against AoN or existing code as `(UNVERIFIED — please check)`.

## Context you must load before planning

### Read these files with the `view` tool, in this order

1. `.claude/context/current_state.md`
2. `.claude/context/architecture.md`
3. `.claude/context/conventions.md`
4. `.claude/context/pitfalls.md`
5. `.claude/project_reference/DECISIONS.md` — focus on D11 through D18
6. `.claude/project_reference/ROADMAP.md`

### Then read the Pass 3a implementation

7. `pf2e/actions.py`
8. `pf2e/character.py`
9. `pf2e/combat_math.py`
10. `pf2e/tactics.py`
11. `sim/scenario.py`

### AoN research

- Initiative rules (https://2e.aonprd.com/Rules.aspx?ID=2127)
- Damage resolution order (https://2e.aonprd.com/Rules.aspx?ID=2189)
- Shield Block (https://2e.aonprd.com/Rules.aspx?ID=2180)
- Intercept Attack (https://2e.aonprd.com/Actions.aspx?ID=3305)
- Temporary Hit Points (https://2e.aonprd.com/Rules.aspx?ID=2321)
- Reactions (https://2e.aonprd.com/Rules.aspx?ID=2432)
