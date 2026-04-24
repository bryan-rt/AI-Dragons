# Checkpoint 4.6: Repo Restructuring for Long-Term Project Design

## Context

A staging directory `project_restructure_docs/` was added to the repo containing context files that need to be migrated into the proper repository structure. These files establish the project's long-term documentation system — `CLAUDE.md` for the CLI agent, `.claude/context/` for reference docs, `.claude/briefs/` for historical briefs, and `characters/` for canonical character data.

This is a pure restructuring checkpoint. **No code changes, no test changes, no behavior changes.** Files move from the staging directory to their permanent locations.

You are implementing the migration below. Do not improvise file locations. Do not rewrite the content of any staged file — they are authoritative as delivered.

## Scope

### What to do

1. Move staged context files to their proper repo locations
2. Populate `.claude/briefs/` with every historical brief from `/mnt/user-data/outputs/` if any exist locally, or note that they need to be copied in manually
3. Verify the staging directory is empty after migration, then remove it
4. Commit with a clear message

### What NOT to do

- Do not modify the content of any file being moved. They are delivered as authoritative.
- Do not add new content to the context files (e.g., don't "helpfully" update ROADMAP.md based on pending work). That's the user's responsibility after restructuring completes.
- Do not touch any production code (`pf2e/`, `sim/`, `tests/`).
- Do not add a CLAUDE.md to subdirectories — only the root CLAUDE.md is in scope.
- Do not run the CLI migration files through formatters or style tools. They are markdown; leave them as-is.

## Pre-implementation: read existing code

Call `view` on:

- `project_restructure_docs/` — confirm the staged files are present
- `project_restructure_docs/SETUP_GUIDE.md` — read this for context on the intended structure
- The repo root — confirm no existing `CLAUDE.md` or `.claude/` directory conflicts with the migration
- `.gitignore` — verify it does not exclude `.claude/` or `characters/` (if it does, that's a bug to fix as part of this checkpoint)

List expected staged files:

```
project_restructure_docs/
├── SETUP_GUIDE.md
├── claude_project_files/
│   ├── PROJECT_INSTRUCTIONS.md
│   ├── ROADMAP.md
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   ├── CHARACTERS.md
│   └── RULES_CITATIONS.md
└── repo_files/
    ├── CLAUDE.md
    ├── .claude/
    │   ├── briefs/
    │   │   └── README.md
    │   └── context/
    │       ├── architecture.md
    │       ├── conventions.md
    │       ├── current_state.md
    │       └── pitfalls.md
    └── characters/
        ├── README.md
        └── aetregan.json
```

Verify all these files exist before proceeding. If any are missing, stop and report.

## Implementation Steps

### Step 1: Create repo directory structure

From repo root:

```bash
mkdir -p .claude/context
mkdir -p .claude/briefs
mkdir -p characters
```

These are the permanent homes for the staged content.

### Step 2: Move the CLI-facing files into the repo structure

Move these files from `project_restructure_docs/repo_files/` to their permanent locations:

| Staged location | Final location |
|---|---|
| `project_restructure_docs/repo_files/CLAUDE.md` | `CLAUDE.md` (repo root) |
| `project_restructure_docs/repo_files/.claude/context/architecture.md` | `.claude/context/architecture.md` |
| `project_restructure_docs/repo_files/.claude/context/conventions.md` | `.claude/context/conventions.md` |
| `project_restructure_docs/repo_files/.claude/context/current_state.md` | `.claude/context/current_state.md` |
| `project_restructure_docs/repo_files/.claude/context/pitfalls.md` | `.claude/context/pitfalls.md` |
| `project_restructure_docs/repo_files/.claude/briefs/README.md` | `.claude/briefs/README.md` |
| `project_restructure_docs/repo_files/characters/README.md` | `characters/README.md` |
| `project_restructure_docs/repo_files/characters/aetregan.json` | `characters/aetregan.json` |

Use `git mv` for each file so history is preserved:

```bash
git mv project_restructure_docs/repo_files/CLAUDE.md CLAUDE.md
git mv project_restructure_docs/repo_files/.claude/context/architecture.md .claude/context/architecture.md
git mv project_restructure_docs/repo_files/.claude/context/conventions.md .claude/context/conventions.md
git mv project_restructure_docs/repo_files/.claude/context/current_state.md .claude/context/current_state.md
git mv project_restructure_docs/repo_files/.claude/context/pitfalls.md .claude/context/pitfalls.md
git mv project_restructure_docs/repo_files/.claude/briefs/README.md .claude/briefs/README.md
git mv project_restructure_docs/repo_files/characters/README.md characters/README.md
git mv project_restructure_docs/repo_files/characters/aetregan.json characters/aetregan.json
```

### Step 3: Handle the web-client-only files

The files in `project_restructure_docs/claude_project_files/` are not meant to be committed as top-level repo files — they live in the Claude Project web interface (uploaded as Knowledge by the user separately).

**However, keeping a reference copy in the repo is valuable** so that the content is version-controlled and future agents can read them for context.

Create a new directory `.claude/project_reference/` and move these files there:

```bash
mkdir -p .claude/project_reference
git mv project_restructure_docs/claude_project_files/PROJECT_INSTRUCTIONS.md .claude/project_reference/PROJECT_INSTRUCTIONS.md
git mv project_restructure_docs/claude_project_files/ROADMAP.md .claude/project_reference/ROADMAP.md
git mv project_restructure_docs/claude_project_files/ARCHITECTURE.md .claude/project_reference/ARCHITECTURE.md
git mv project_restructure_docs/claude_project_files/DECISIONS.md .claude/project_reference/DECISIONS.md
git mv project_restructure_docs/claude_project_files/CHARACTERS.md .claude/project_reference/CHARACTERS.md
git mv project_restructure_docs/claude_project_files/RULES_CITATIONS.md .claude/project_reference/RULES_CITATIONS.md
```

Add a `.claude/project_reference/README.md` explaining the directory's purpose:

```markdown
# Project Reference

These files are the same content that lives in the Claude Project web interface's Instructions and Knowledge sections. They are committed here as a version-controlled reference, so:

1. If the web client copies drift, the repo copies are authoritative
2. Future CLI agents can read them for full project context
3. Changes to project-level docs are version-controlled with the code

**When updating these files**, update in one place then sync to the other. The web client is where Claude reads them in conversation; the repo is where they're backed up and versioned.

## File roles

- `PROJECT_INSTRUCTIONS.md` — Pasted into the Claude Project Instructions field (always-loaded baseline)
- `ROADMAP.md` — Checkpoint status and roadmap
- `ARCHITECTURE.md` — System design and module layout
- `DECISIONS.md` — Architectural decision log
- `CHARACTERS.md` — Party composition reference
- `RULES_CITATIONS.md` — Verified AoN rule URLs

## Update cadence

- After a checkpoint completes, update `ROADMAP.md` and consider whether any other file needs updates.
- New architectural decisions append entries to `DECISIONS.md`.
- New PF2e rules consulted get added to `RULES_CITATIONS.md`.
- Character changes update `CHARACTERS.md`.
- Rarely-changing: `PROJECT_INSTRUCTIONS.md` and `ARCHITECTURE.md`.
```

### Step 4: Move or delete the SETUP_GUIDE.md

The SETUP_GUIDE was a one-time onboarding document. Now that setup is complete, archive it to `.claude/project_reference/`:

```bash
git mv project_restructure_docs/SETUP_GUIDE.md .claude/project_reference/SETUP_GUIDE.md
```

### Step 5: Verify staging directory is empty, then remove it

```bash
# Should show empty directories only
find project_restructure_docs -type f

# Remove the now-empty staging directory
rm -rf project_restructure_docs
```

Use `rm -rf` (not `git rm -r`) since the staging directory was never meant to be permanent.

### Step 6: Populate `.claude/briefs/`

This step cannot be done by the CLI agent alone — the user must provide the historical brief markdown files from their local system (`/mnt/user-data/outputs/` in the original context).

Create a placeholder note that the user will need to act on:

Create `.claude/briefs/PLACEHOLDER.md`:

```markdown
# Briefs to be Added

This directory should contain all historical briefs from the project. Copy the following files here (the user has them locally from past conversations):

- `pf2e_sim_task_brief_pass1.md`
- `pf2e_sim_task_brief_pass1_5.md`
- `pf2e_sim_task_brief_pass2_5.md`
- `checkpoint_0_5_cleanup_brief.md`
- `checkpoint_1_pass_1_brief.md`
- `checkpoint_1_pass_2_brief.md`
- `checkpoint_1_pass_3_brief.md`
- `checkpoint_2_pass_1_brief.md`
- `checkpoint_2_pass_2_brief.md`
- `checkpoint_2_pass_3_brief.md`
- `checkpoint_3_pass_1_brief.md`
- `checkpoint_3_pass_2_brief.md`
- `checkpoint_3_pass_3_brief.md`
- `checkpoint_4_pass_1_brief.md`
- `checkpoint_4_pass_2_brief.md`
- `checkpoint_4_pass_3_brief.md`
- `checkpoint_4_5_aetregan_reconciliation.md`
- `checkpoint_5_1_pass_1_brief.md`
- `checkpoint_5_1_pass_2_brief.md`
- `checkpoint_5_1_pass_3a_brief.md`
- `checkpoint_4_6_restructure_brief.md` (this brief — add it too)

Not all may be present locally — that's fine. Copy what you have.

Delete this PLACEHOLDER.md file once the briefs have been added.
```

### Step 7: Update `.gitignore` if needed

Check `.gitignore`. If it excludes `.claude/` or `characters/`, remove those exclusions. Neither should be gitignored.

If the repo doesn't have a `.gitignore`, skip this step.

### Step 8: Verify repo structure

Run these verification commands and include their output in the commit message or a follow-up comment:

```bash
# Confirm the structure
find CLAUDE.md .claude characters -type f | sort

# Confirm staging is gone
ls project_restructure_docs 2>&1 | head -5

# Confirm tests still pass (this checkpoint should not have touched production code)
pytest tests/ -v 2>&1 | tail -20
```

Expected outputs:

1. The `find` should list approximately these files (plus any briefs the user adds):
   ```
   .claude/briefs/PLACEHOLDER.md
   .claude/briefs/README.md
   .claude/context/architecture.md
   .claude/context/conventions.md
   .claude/context/current_state.md
   .claude/context/pitfalls.md
   .claude/project_reference/ARCHITECTURE.md
   .claude/project_reference/CHARACTERS.md
   .claude/project_reference/DECISIONS.md
   .claude/project_reference/PROJECT_INSTRUCTIONS.md
   .claude/project_reference/README.md
   .claude/project_reference/ROADMAP.md
   .claude/project_reference/RULES_CITATIONS.md
   .claude/project_reference/SETUP_GUIDE.md
   CLAUDE.md
   characters/README.md
   characters/aetregan.json
   ```

2. The `ls` should report that `project_restructure_docs` does not exist.

3. Test suite should report **207 passed** (or whatever the CP4.5 baseline is). No changes from CP4.5 baseline expected.

### Step 9: Commit

```bash
git add -A
git commit -m "CP4.6: Restructure repo for long-term project design

- Move staged context files from project_restructure_docs/ to final locations
- Add CLAUDE.md at repo root for CLI agent context
- Add .claude/context/ for agent-facing reference docs
- Add .claude/project_reference/ as version-controlled mirror of Claude Project knowledge
- Add .claude/briefs/ scaffolding for historical brief archive
- Add characters/ directory with aetregan.json canonical data
- Remove project_restructure_docs staging directory

No production code changes. All 207 tests continue to pass."
```

Then `git push`.

## Validation checklist

- [ ] All 8 CLI-facing files moved to `.claude/context/`, `.claude/briefs/`, `CLAUDE.md`, or `characters/`
- [ ] All 7 web-client files (+ SETUP_GUIDE) moved to `.claude/project_reference/`
- [ ] `.claude/project_reference/README.md` created explaining the directory
- [ ] `.claude/briefs/PLACEHOLDER.md` created to prompt user action
- [ ] `project_restructure_docs/` directory removed
- [ ] `.gitignore` does not exclude `.claude/` or `characters/`
- [ ] `find CLAUDE.md .claude characters -type f` shows expected structure
- [ ] `pytest tests/ -v` shows **207 passed** — no regression
- [ ] Commit made with clear checkpoint message
- [ ] Pushed to GitHub

## Common pitfalls

**Don't edit file contents during the move.** Several of these files have specific formatting (markdown tables, code blocks). `git mv` preserves content perfectly; don't be tempted to "clean up" or "improve" the files while moving them. The user authorized their current content.

**Don't commit `project_restructure_docs/` before removing it.** If you `git add -A` while the staging directory still exists, it will get committed. Either remove it before the commit, or use `git add` with specific paths.

**`git mv` for tracked files only.** If `project_restructure_docs/` was added in a previous commit (which it was, when the user placed the files there), `git mv` is correct. If any file is untracked, use `mv` then `git add` separately.

**The CP5.1 Pass 3a implementation work is unaffected.** This restructuring is orthogonal. Tests should still pass at 207 (or whatever baseline is current). If tests fail, you may have accidentally moved a production file — revert and investigate.

**Don't add this brief to `.claude/briefs/` yourself.** The user will provide it (along with other historical briefs) when populating the directory. Just leave the PLACEHOLDER.md as a reminder.

**Hidden directory warning.** `.claude/` starts with a dot. On some shells this can be easy to miss with `ls` (need `ls -la`) but `find` and `git` handle it correctly. Verify with `ls -la` if uncertain.

**Path separators.** Use forward slashes in the brief's paths regardless of OS. Git handles normalization.

## What comes after

Once this restructuring is complete:

1. User manually copies historical briefs into `.claude/briefs/` from their local outputs folder
2. User deletes the PLACEHOLDER.md
3. User sets up the Claude Project web interface per the SETUP_GUIDE.md instructions now archived in `.claude/project_reference/`
4. Work continues on CP5.1 Pass 3a (if that implementation is still pending) or CP5.1 Pass 3b (if 3a completed)

This brief itself should be added to `.claude/briefs/` as `checkpoint_4_6_restructure_brief.md` by the user once they're populating that directory.

The project now has proper long-term documentation infrastructure. Future sessions start with full context loaded. Decisions are preserved indefinitely. The architecture scales from solo project to small team to public product over time.
