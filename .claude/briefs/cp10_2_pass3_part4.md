# CP10.2 — Trait System: Pass 3 Brief
## Part 4 of 6: Test Names (tests/test_traits.py)

**TraitDef structure (5)**
- `test_traitdef_is_frozen`
- `test_all_9_slugs_in_registry`
- `test_fear_is_descriptor_not_immunity`
- `test_immunity_traits_have_nonempty_tag`
- `test_map_traits_have_empty_immunity_tag`

**is_immune() (8)**
- `test_is_immune_mental_vs_mental_target` → `True`
- `test_is_immune_mental_vs_empty_tags` → `False`
- `test_is_immune_emotion_vs_emotion_target` → `True`
- `test_is_immune_fear_vs_emotion_target` → `False`
- `test_is_immune_unknown_slug_skipped` → `False`
- `test_is_immune_empty_action_traits` → `False`
- `test_is_immune_multiple_traits_one_match` → `True`
- `test_is_immune_auditory_vs_auditory` → `True`

**has_trait() (8)**
- `test_has_trait_attack_is_map` → `True`
- `test_has_trait_flourish_is_flourish` → `True`
- `test_has_trait_open_is_open` → `True`
- `test_has_trait_press_is_press` → `True`
- `test_has_trait_mental_is_immunity` → `True`
- `test_has_trait_fear_is_descriptor` → `True`
- `test_has_trait_unknown_slug` → `False`
- `test_has_trait_empty_set` → `False`

**Character.immunity_tags (4)**
- `test_aetregan_immunity_tags_empty`
- `test_rook_immunity_tags_empty`
- `test_immunity_tags_default_is_frozenset`
- `test_synthetic_character_with_immunity_tags`
  *(build a Character with `{"mental"}`, verify field)*

**CombatantSnapshot.used_flourish_this_turn (4)**
- `test_used_flourish_defaults_false`
- `test_used_flourish_on_snapshot_from_state`
- `test_reset_turn_state_clears_flourish`
- `test_used_flourish_independent_across_snapshots`

**Regression (1)**
- `test_ev_7_65_regression`
  *(use `evaluate_tactic(STRIKE_HARD, ctx)` pattern)*

**Total: ~30 tests → 597 → ~627**
