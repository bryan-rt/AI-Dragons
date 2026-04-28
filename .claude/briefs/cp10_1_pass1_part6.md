# CP10.1 — Roll Foundation: Pass 1 Brief
## Part 6 of 6: Open Questions, Validation Checklist & Pass 3 Order

---

## Open Questions for Pass 2

**Q1** — Flat check audit: How many places in `actions.py`
hardcode hidden/concealment probability as an inline fraction?
Report each call site (file, line, expression). These will
migrate to `flat_check()` in CP10.7.

**Q2** — D20Outcomes migration timing: Recommendation is
Option B — leave in `combat_math.py` through CP10.3, migrate
when BonusTracker integration already touches all callers.
Confirm or flag if there's a reason to move now.

**Q3** — Fortune distribution math location: When CP10.4
chassis evaluators need it, should
`enumerate_d20_outcomes_with_fortune()` live in `rolls.py`
or `combat_math.py`? Recommendation: `rolls.py` (roll
mechanics concern, not character math).

**Q4** — Nat-1/nat-20 as explicit concept: Should
`RollType.STANDARD` carry `has_degree_shift: bool = True`?
Deferred unless you want to encode it now.

---

## Validation Checklist

- [ ] `pf2e/rolls.py` created, no imports from other `pf2e/`
- [ ] `flat_check(5)==0.80`, `flat_check(11)==0.50`,
      `flat_check(15)==0.30`
- [ ] `flat_check(21)==0.0`, `flat_check(0)==1.0`
- [ ] `FortuneState.combine(True,True)==CANCELLED`
- [ ] `FortuneState.combine(True,False)==FORTUNE`
- [ ] All 4 FortuneState variants exist
- [ ] Both RollType variants exist
- [ ] `git diff --name-only` shows only 2 new files
- [ ] `pytest tests/ -v` → 578 pass + ~19 new, total ~597
- [ ] EV 7.65 (24th verification)

---

## Pass 3 Implementation Order

1. Create `pf2e/rolls.py` exactly as specified in Parts 2–3
2. Create `tests/test_cp10_1_rolls.py` with all 19 tests
3. Run `pytest tests/ -v` — confirm 578 existing pass
4. Answer Q1: search `actions.py`, report call sites
5. Verify EV 7.65 using existing tactic regression pattern
6. Paste pytest summary + audit results for Pass 2 review
