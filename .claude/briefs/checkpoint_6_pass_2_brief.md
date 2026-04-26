# CP6 — Pass 2 Brief: Corrections and Refinements

(Full brief content in conversation history. Saved 2026-04-25.)

Key decisions:
- Top 5 plans via seed variation (seeds 42-46), true branching deferred to CP7
- Action economy reset (_reset_turn_state) is critical infrastructure
- STAND action required for multi-round prone recovery
- Condition durations via dict field on snapshots (Option A)
- sim/solver.py as new module, sim/search.py unchanged
- --full-combat CLI flag, single-round mode preserved

22-step implementation order. Target ~458 tests.
