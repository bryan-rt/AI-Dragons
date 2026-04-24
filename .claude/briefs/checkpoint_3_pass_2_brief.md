# Checkpoint 3 Pass 2: Corrections

## Context

Your Pass 1 plan is strong. The file format grammar, dataclass shape, loader separation, factory relocation (to `sim/party.py`), integration tests, and module structure are all approved as-is. This Pass 2 covers six concrete corrections before Pass 3 implementation.

**Do NOT rewrite the whole plan.** Apply the corrections below and output a compact updated plan. Unchanged sections can be summarized as "unchanged from Pass 1."

**Standing rules apply.** Verify against AoN, cite URLs, surface discrepancies, don't expand scope, read existing code before changing it.

---

## Corrections to Apply

### C.1 Fix the wrong token in the example scenario — CRITICAL

Dalai's ally token is `b` (Bard), NOT `d`. Your example scenario grid has:

```
. . . . i d . . . .
```

This is wrong. `d` is not in `_ALLY_TOKENS` (`{"c", "g", "b", "i"}`), so `parse_map` would fall through to the generic named-position branch, and then `TOKEN_TO_FACTORY["d"]` would raise `KeyError` because there's no factory registered for `d`.

**Fix**: Change that grid row to:

```
. . . . i b . . . .
```

Update the Section 8 grid analysis accordingly: "Row 6: i at (6,4), b at (6,5)."

The remainder of the grid is correct: `c` at (5,5), `g` at (5,6), `m` at (5,7) with `m` auto-numbering to `m1`. Banner at (5,5). Anthem active. Expected EV = 8.55 is still the right target.

Read `sim/grid.py`'s `_ALLY_TOKENS` definition before writing Pass 3 to confirm the exact token set. If the agent in Checkpoint 2 made any different decision about Dalai's token, surface it.

### C.2 Require commander token; other party tokens are optional

Your Section 12.1 proposed: "if a token isn't in the grid, that character is absent from the scenario." That's reasonable for squadmates but wrong for the commander.

**A scenario without a commander has nothing to evaluate tactics for.** The commander IS the tactical agent. Split the rule:

- Commander token `c` is **required**. Missing → `ScenarioParseError("No commander ('c') in grid")`.
- Squadmate tokens `g`, `b`, `i` are **optional**. Missing → that character is not in `scenario.squadmates` (absent from this encounter).

Update Section 12.1 with this asymmetry. For Pass 3, the loader must explicitly check for commander presence before building the context.

### C.3 Reuse `make_rook_combat_state()` instead of duplicating armor logic

Your `_build_combatant` hardcodes `state.current_speed = 20` for Rook. But `sim/party.py` already has `make_rook_combat_state()` which handles this. Use it:

```python
def _build_combatant(
    token: str, pos: Pos, anthem_active: bool,
) -> CombatantState:
    if token == "g":  # Rook — full plate speed penalty applied by helper
        state = make_rook_combat_state(anthem_active=anthem_active)
    else:
        factory = TOKEN_TO_FACTORY[token]
        state = CombatantState.from_character(
            factory(), anthem_active=anthem_active,
        )
    state.position = pos
    return state
```

This eliminates the duplication and keeps all armor penalty logic in one place (the helper function in `sim/party.py`).

If a future party member needs armor speed penalties, add a similar helper for them rather than scattering the logic.

### C.4 Simplify `TOKEN_TO_FACTORY`

The tuple form `{"c": ("Aetregan", make_aetregan), ...}` is overengineered. The name is already accessible via `factory().name`. Use a plain dict:

```python
TOKEN_TO_FACTORY: dict[str, Callable[[], Character]] = {
    "c": make_aetregan,
    "g": make_rook,
    "b": make_dalai,
    "i": make_erisen,
}

COMMANDER_TOKEN = "c"
```

If user-facing error messages need a display name, extract it from the character at error-construction time.

### C.5 Document enemy token naming in [enemies] section

Clarify in the file format docs: `[enemies]` lines always use the **auto-numbered token** (`m1`, `m2`, `M1`, etc.), never the base letter. A grid with one `m` produces token `m1` (not `m`), and the `[enemies]` line must read `m1 name=...`.

Add a line to Section 1's grammar table or Section 4's "Line format":

> "Enemy tokens in `[enemies]` match the auto-numbered form produced by the grid parser (`m1`, `m2`, `M1`, etc.), regardless of whether there is only one enemy of that type."

This prevents confusion where a user writes `[enemies] m name=...` and gets an error that token `m1` has no stats.

### C.6 Verify `CombatantState.from_character` signature before Pass 3

Your `_build_combatant` assumes `CombatantState.from_character(char, position=pos, anthem_active=flag)` works. But I'm not certain `position` was added as a `from_character` kwarg in Checkpoint 2 — it may only exist as a field with default `(0, 0)`, requiring `state.position = pos` after construction.

Before Pass 3 implementation, read `pf2e/character.py` and confirm the exact `from_character` signature. If `position` is not a `from_character` parameter:

- **Option A**: Add it to `from_character` in Pass 3 (small foundation change).
- **Option B**: Build the state first, then assign `state.position = pos` as a separate step.

Both work. Option B requires no foundation change and matches the pattern `make_rook_combat_state(anthem_active=...)` + `state.position = pos` I showed in C.3. Recommend Option B unless there's a reason to touch `from_character`.

Same check for `anthem_active`: confirm it's a `from_character` kwarg. If not, set it post-construction.

---

## Confirmed as-is from Pass 1

- File format grammar (sections, `key = value`, comments, coordinates as `row, col`, `.scenario` extension)
- Error handling table and `ScenarioParseError`
- `Scenario` dataclass shape (frozen, with mutable lists inside)
- Separation of `load_scenario()` (I/O) and `parse_scenario()` (pure)
- `build_tactic_context()` constructing fresh `GridSpatialQueries` per call
- Move of factories from `tests/fixtures.py` to `sim/party.py` with re-export shim
- Example scenario file structure (with C.1 token fix)
- Integration tests A–E
- Module structure: `sim/scenario.py`, `sim/party.py`, `scenarios/checkpoint_1_strike_hard.scenario`, `tests/test_scenario.py`
- `[banner]` section authoritative; grid `B`/`*` token as fallback
- Multi-word enemy names deferred (single-word only)
- Carried banner deferred (planted-only in Checkpoint 3)

---

## Output Format

Produce a compact Pass 2 plan with:

1. **Corrections applied** — brief confirmation of each C.1–C.6 item with updated values
2. **Updated Section 3** with the simplified `TOKEN_TO_FACTORY` and fixed `_build_combatant`
3. **Updated Section 8** with the corrected example scenario (use `b`, not `d`) and corrected grid analysis
4. **Updated Section 12.1** splitting commander-required from squadmate-optional
5. **Any signature findings from Section C.6** — note what `from_character` actually accepts and which implementation option you'll use
6. **Unchanged from Pass 1** — one-line summary

Aim for 1-2 pages. This is surgical, not a rewrite.

When you're done, output the Pass 2 plan as a single document. Wait for review before any code is written.

---

## What Happens Next

1. You produce this Pass 2 plan.
2. I review and confirm (or flag anything I missed).
3. We move to Pass 3 implementation.
4. Code lands, tests pass, Checkpoint 3 closes.
