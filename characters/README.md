# Briefs Archive

Historical design and implementation briefs for every checkpoint. The CLI agent references these when working on a specific checkpoint or when needing context on past decisions.

## Organization

Briefs are named `checkpoint_<num>_pass_<num>_brief.md` where applicable:

- `pf2e_sim_task_brief_pass1.md` — initial project architecture
- `pf2e_sim_task_brief_pass1_5.md` — foundation refinement
- `pf2e_sim_task_brief_pass2_5.md` — further foundation
- `checkpoint_0_5_cleanup_brief.md` — CP0.5 corrections
- `checkpoint_1_pass_1_brief.md` — CP1 architecture
- `checkpoint_1_pass_2_brief.md` — CP1 refinements
- `checkpoint_1_pass_3_brief.md` — CP1 implementation
- `checkpoint_2_pass_1_brief.md` through `checkpoint_2_pass_3_brief.md`
- `checkpoint_3_pass_1_brief.md` through `checkpoint_3_pass_3_brief.md`
- `checkpoint_4_pass_1_brief.md` through `checkpoint_4_pass_3_brief.md`
- `checkpoint_4_5_aetregan_reconciliation.md` — CP4.5 reconciliation
- `checkpoint_5_1_pass_1_brief.md` — CP5.1 architecture (turn evaluator)
- `checkpoint_5_1_pass_2_brief.md` — CP5.1 refinements
- `checkpoint_5_1_pass_3a_brief.md` — CP5.1 foundation implementation (active)
- `checkpoint_5_1_pass_3b_brief.md` — CP5.1 algorithms (future)
- `checkpoint_5_1_pass_3c_brief.md` — CP5.1 actions and integration (future)

## Three-Pass Methodology

Each checkpoint follows a three-pass design before implementation:

**Pass 1 (Architecture):** High-level design — data model, algorithm choices, scope. Ends with review asks for the user.

**Pass 2 (Refinements):** Incorporates feedback, resolves open questions, names defaults for undecided items.

**Pass 3 (Implementation):** Step-by-step brief for the CLI agent. Specific file paths, code skeletons, tests, validation checklist, pitfalls.

For large checkpoints (CP5.1), Pass 3 splits into sub-briefs (3a, 3b, 3c).

## How to Use These Briefs

### When implementing a checkpoint:
Read the Pass 3 brief for that checkpoint. Follow it exactly. The brief specifies:
- What to implement (and what NOT to implement)
- Files to read first
- Step-by-step implementation order
- Tests to write
- Validation checklist
- Common pitfalls for that specific work

### When reviewing prior decisions:
Read the Pass 1 brief for architectural reasoning. Pass 2 for how decisions were refined based on feedback. Decision rationale often lives in Pass 1 and Pass 2, not just Pass 3.

### When flagging discrepancies:
If implementation diverges from brief, reference the specific brief and step. This helps triage: is the brief wrong, or is the implementation wrong?

## Brief Writing Conventions

Briefs have consistent structure:

1. **Context** — what checkpoint this is, what's been decided, what's coming
2. **Scope** — what to implement, what NOT to implement
3. **Pre-implementation: read existing code** — files to `view` first
4. **Implementation** — step-by-step instructions with code skeletons
5. **Validation checklist** — items to tick off before considering complete
6. **Common pitfalls** — gotchas specific to this work
7. **What comes after** — where this fits in the larger plan

The Pass 3 briefs in particular are self-contained: a fresh CLI agent should be able to implement the checkpoint from the brief alone, without outside context.

## Preserving History

All briefs stay in this directory indefinitely. When checkpoints are superseded or their decisions reversed, the historical brief remains. The CHANGELOG documents what actually shipped; the briefs document what was planned.

This gives us a complete paper trail for architectural decisions, which is important for:
- Understanding why current code is shaped the way it is
- Avoiding relitigating decisions that were already made
- Training future agents / maintainers on the project's reasoning style
