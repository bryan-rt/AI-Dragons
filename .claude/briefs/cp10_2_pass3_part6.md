# CP10.2 — Trait System: Pass 3 Brief
## Part 6 of 6: Common Pitfalls

---

**1. fear has no immunity_tag — intentional.**
`is_immune({"fear"}, {"emotion"})` must return `False`.
Fear immunity flows through the emotion trait in PF2e.
Don't "fix" this — it's correct by design.

**2. Unknown slugs must be silently skipped.**
Weapon traits (`"finesse"`, `"agile"`, `"reach"`) appear
in action trait sets and must not raise or crash
`is_immune()` or `has_trait()`.

**3. Don't create a second with_pc_update call.**
Fold `used_flourish_this_turn=False` into the existing
reset call in `_reset_turn_state()`.

**4. Don't add immunity_tags to EnemySnapshot.**
CP10.4 evaluators access immunity via
`snap.character.immunity_tags` on PC snapshots.
Enemy immunity handling is deferred.

**5. No flourish enforcement yet.**
`used_flourish_this_turn` is data-only infrastructure.
The beam search does not check it until CP10.4.

**6. from_combatant_state() needs no change.**
`used_flourish_this_turn=False` default means the
existing construction path is already correct.

---

*End of CP10.2 Pass 3 Brief.*
