# Migration Setup Guide

This guide walks through setting up the Claude Project and committing the repo-side context files.

## Step 1: Create the Claude Project

1. Go to [claude.ai](https://claude.ai) and create a new Project
2. Name it: "PF2e Tactical Simulator" (or whatever you prefer)
3. In the Project Instructions field, paste the entire contents of `claude_project_files/PROJECT_INSTRUCTIONS.md`

## Step 2: Upload Knowledge Files

In the Project, upload these files to Knowledge:

- `claude_project_files/ROADMAP.md`
- `claude_project_files/ARCHITECTURE.md`
- `claude_project_files/DECISIONS.md`
- `claude_project_files/CHARACTERS.md`
- `claude_project_files/RULES_CITATIONS.md`

These become retrievable references. Claude pulls the relevant ones based on conversation topic.

## Step 3: Also upload Aetregan's JSON

Upload `repo_files/characters/aetregan.json` to Knowledge as well. This gives the Project direct access to Aetregan's canonical data without needing the repo.

## Step 4: Commit Repo-Side Files

From your repo root:

```bash
# Create the directory structure
mkdir -p .claude/context .claude/briefs characters

# Copy files in (adjust paths based on where you downloaded them)
cp /path/to/repo_files/CLAUDE.md .
cp /path/to/repo_files/.claude/context/*.md .claude/context/
cp /path/to/repo_files/.claude/briefs/README.md .claude/briefs/
cp /path/to/repo_files/characters/README.md characters/
cp /path/to/repo_files/characters/aetregan.json characters/

# Also copy any existing briefs from /mnt/user-data/outputs/ that you have
# Those go in .claude/briefs/ with their original filenames
```

For the briefs, copy over all the markdown brief files you've accumulated from our conversations. Expected filenames:

```
pf2e_sim_task_brief_pass1.md
pf2e_sim_task_brief_pass1_5.md
pf2e_sim_task_brief_pass2_5.md
checkpoint_0_5_cleanup_brief.md
checkpoint_1_pass_1_brief.md
checkpoint_1_pass_2_brief.md
checkpoint_1_pass_3_brief.md
checkpoint_2_pass_1_brief.md
checkpoint_2_pass_2_brief.md
checkpoint_2_pass_3_brief.md
checkpoint_3_pass_1_brief.md
checkpoint_3_pass_2_brief.md
checkpoint_3_pass_3_brief.md
checkpoint_4_pass_1_brief.md
checkpoint_4_pass_2_brief.md
checkpoint_4_pass_3_brief.md
checkpoint_4_5_aetregan_reconciliation.md
checkpoint_5_1_pass_1_brief.md
checkpoint_5_1_pass_2_brief.md
checkpoint_5_1_pass_3a_brief.md
```

Not all may exist — that's fine. Copy what you have.

## Step 5: Commit and Push

```bash
git add CLAUDE.md .claude/ characters/
git commit -m "Add Claude Project context and briefs archive"
git push
```

## Step 6: Start a New Conversation

- Open the Claude Project you created
- Start a new chat within it
- Say something like: "Ready to continue work on the PF2e simulator. What's our current state?"

A fresh Claude should:
1. Read the Project Instructions (automatic)
2. Reference `ROADMAP.md` to confirm current checkpoint
3. Reference `DECISIONS.md` if architecture questions arise
4. Be able to pick up work with minimal re-explanation

## Step 7: Update `current_state.md` After Each Checkpoint

The CLI agent (or you manually) should update `.claude/context/current_state.md` after completing each checkpoint:

- New test count
- Active work description
- Any newly-known TODOs

This keeps the CLI agent's context fresh between sessions.

## Step 8 (Optional): Update Project Instructions Over Time

If major architectural decisions shift or new conventions emerge, update `PROJECT_INSTRUCTIONS.md` accordingly. Re-paste into the Project settings.

## What This Migration Gives You

**Before:** Context accumulates in one long conversation. When it gets too long, compaction happens and subtle details can get lost. Starting a new conversation requires re-explaining everything.

**After:**
- New conversations start with full context loaded automatically
- Knowledge files provide detailed reference on demand
- CLI agent sessions pick up context from `CLAUDE.md` and `.claude/`
- All briefs are version-controlled alongside the code
- Decision rationale is preserved indefinitely

**One thing to understand:** The Web Claude conversations and the CLI agent sessions are now fully parallel — both read their own context from their own sources. You're the bridge. When the Web Claude writes a brief, you paste it to the CLI agent. When the CLI agent finishes implementation, you paste results back to the Web Claude. The context files keep everyone in sync.

## File Structure Summary

```
# In your repo:
AI-Dragons/
├── CLAUDE.md                    # CLI agent reads this first
├── .claude/
│   ├── context/
│   │   ├── architecture.md
│   │   ├── conventions.md
│   │   ├── current_state.md    # Update after each checkpoint
│   │   └── pitfalls.md
│   └── briefs/
│       ├── README.md
│       └── checkpoint_*.md      # All historical briefs
├── characters/
│   ├── README.md
│   └── aetregan.json           # Canonical character data
├── pf2e/                        # Production code (unchanged)
├── sim/                         # Production code (unchanged)
├── scenarios/                   # Production data (unchanged)
├── tests/                       # Tests (unchanged)
├── CHANGELOG.md                 # Version history
└── README.md                    # Project overview

# In the Claude Project:
Project Settings:
├── Instructions: PROJECT_INSTRUCTIONS.md (pasted into settings)
└── Knowledge:
    ├── ROADMAP.md
    ├── ARCHITECTURE.md
    ├── DECISIONS.md
    ├── CHARACTERS.md
    ├── RULES_CITATIONS.md
    └── aetregan.json
```

## Troubleshooting

**Fresh Claude asks too many clarifying questions.** The Instructions might not be verbose enough, or Knowledge files aren't loading. Check that Knowledge files are uploaded and accessible.

**CLI agent diverges from conventions.** Its context may be stale. Have it re-read `CLAUDE.md`, `.claude/context/conventions.md`, and `.claude/context/pitfalls.md` at session start.

**Test count disagreement between Web and CLI context.** `.claude/context/current_state.md` is the source of truth. Update it after every checkpoint and have both interfaces read it.
