# Decision Log

Major architectural decisions with rationale. Append as new decisions are made.

## D1: Two-package architecture (pf2e/ + sim/)

**Decision:** Pure rules engine in `pf2e/`, simulator in `sim/`. Unidirectional dependency.

**Rationale:** The rules engine can potentially be extracted as a standalone library later. Layering enforces discipline — accidentally coupling rules to grid geometry would make the engine untransportable.

**Decided:** CP0, reaffirmed throughout.

## D2: Derive, don't store

**Decision:** Combat numbers computed on demand from character + state. No pre-baked values except static equipment properties and max HP.

**Rationale:** When transient state changes (shield raised, off-guard applied), next derivation sees the new state. No "did I remember to update the cached AC?" bugs.

**Decided:** CP0.

## D3: Frozen Character, mutable CombatantState

**Decision:** `Character` is immutable build data. `CombatantState` wraps it with mutable per-round state.

**Rationale:** A character can participate in multiple hypothetical combat states simultaneously (search tree branches). Sharing the immutable build is safe; mutating state is cheap.

**Decided:** CP0.

## D4: Three-pass checkpoint methodology

**Decision:** Every checkpoint goes through Pass 1 (architecture), Pass 2 (refinements), Pass 3 (implementation). Large checkpoints split Pass 3 further.

**Rationale:** Catches architectural errors before code is written. The Aetregan Wis correction, mortar EV correction, and banner aura expansion were all caught in Pass 2 reviews before shipping to Pass 3.

**Decided:** CP0.5, refined through CP4.

## D5: Protocol-based spatial queries

**Decision:** `SpatialQueries` is a Protocol, with `MockSpatialQueries` for tests and `GridSpatialQueries` for real grids.

**Rationale:** Tactics evaluation is grid-independent. CP1 could validate tactic math without building the grid first. CP2 swapped in real grid and same EV 8.55 emerged. Clean abstraction.

**Decided:** CP1.

## D6: PF2e 5/10 diagonal for distance, uniform for pathfinding

**Decision:** `distance_ft()` uses strict 5/10 alternation (rules-correct). BFS pathfinding uses uniform 5-ft step (simplified).

**Rationale:** Point-to-point queries (emanation, reach, auras) must be rules-correct. BFS with strict alternation requires Dijkstra with state-tracking; uniform simplification underestimates long diagonal paths by ~15% max. Acceptable for tactical advice; biases toward false-negative reachability (conservative).

**Decided:** CP2.

## D7: Banner aura expansion when planted

**Decision:** Carried banner = 30-ft emanation from commander. Planted banner = 40-ft burst from planted position.

**Rationale:** The Plant Banner feat explicitly expands the emanation into a burst +10 ft. This was missed in initial design, caught during CP4 verification. Correctness fix.

**Source:** [AoN Plant Banner](https://2e.aonprd.com/Feats.aspx?ID=7796).

**Decided:** CP4.

## D8: banner_planted required parameter

**Decision:** `GridSpatialQueries.__init__` requires `banner_planted: bool` with no default.

**Rationale:** Silent default would hide incorrect usage. Every call site must make an explicit choice, which surfaces the "is this banner carried or planted?" question at construction time.

**Decided:** CP4.

## D9: Carried banner follows commander

**Decision:** When `banner_planted=False`, the aura's center is the commander's current position, not the stored `banner_position`.

**Rationale:** Bryan's Aetregan carries the banner on her backpack. Aura moves with her. The stored `banner_position` is informational (for debugging) but ignored spatially.

**Decided:** CP4.5.

## D10: Aetregan reconciliation from Pathbuilder JSON

**Decision:** Character sheet data is canonical. `make_aetregan()` must match the JSON exactly.

**Rationale:** Pre-JSON assumptions had multiple errors (Cha 12 not 10, Perception trained not expert, Plant Banner assumed not deferred, Defensive Retreat in folio not Shields Up!). JSON is the ground truth.

**Decided:** CP4.5.

## D11: Party preservation + kill/drop scoring

**Decision:** Score = `P(kill) × kill_value − P(drop) × drop_cost + damage_dealt − 0.5 × damage_taken`.

**Rationale:** "Probability of combat victory" is the gold-standard objective. We can't compute it without multi-round simulation, so we proxy with single-round: kills end combat (high weight), drops lose combat (high weight), damage is intermediate currency. Threat-weighted and role-weighted multipliers capture "kill the boss" > "kill a minion" and "save the Bard" > "save the tank."

**Decided:** CP5.1 Pass 1 scoping.

## D12: Kill/drop multiplier is 10 (not 20)

**Decision:** `kill_value = max_hp + 10 × num_attacks`, `drop_cost = max_hp + 10 × role_multiplier`.

**Rationale:** Pass 1 proposed 20, which made kill probability dominate 5:1 over raw damage. Agent's push back for 10 keeps kills preferred without over-weighting speculative kill attempts. Revisit in CP7 with observed behavior.

**Decided:** CP5.1 Pass 2.

## D13: Outcome buckets for damage distributions

**Decision:** Each Strike is `{miss, hit, crit}` with explicit probabilities. Multi-Strike turns compose as probability trees. Low-probability branches pruned at 0.1%.

**Rationale:** Captures "does this crit change the kill outcome?" variance at tractable cost. Full damage PMF is 5-10x more expensive for small accuracy gains. Gaussian approximation is wrong at tails (where P(kill) lives) because PF2e damage is bimodal (miss + hit/crit spike).

**Decided:** CP5.1 Pass 1.

## D14: Hybrid state threading (EV + kill/drop branching)

**Decision:** Actions collapse to EV-updated state *except* when the action's outcome crosses a kill or drop threshold. Those actions branch the search tree into "event happens" and "event doesn't happen" worlds.

**Rationale:** Full expectimax is 10^6 branches per search. Pure EV-collapse loses the "enemy is dead, action 3 targets someone else" semantics. Hybrid branches only at the discontinuities that actually change subsequent action space. Typical round: 4-16 branches per search node.

**Decided:** CP5.1 Pass 1 scoping, confirmed Pass 2 despite agent pushback.

## D15: Beam search K=50/20/10 depth 3

**Decision:** Per-character turn beam search with widening at root. K=50 at depth 1, K=20 at depth 2, K=10 at depth 3.

**Rationale:** Depth matches the 3-action PF2e turn. Widening at root preserves diverse first-action candidates (defensive against horizon effect where "setup action A enables killer combo" would be missed by narrow beam). Pruning narrows as plans crystallize. Modern chess engines use similar structure.

**Decided:** CP5.1 Pass 2.

## D16: Adversarial enemy sub-search

**Decision:** When PC search encounters an enemy's turn, run a sub-search (K=20, depth 3) for enemy's best 3 actions with sign-flipped scoring. Single-best-response (not multi-plan expectimax).

**Rationale:** Full two-sided minimax is exponentially expensive. Single-best-response captures most adversarial signal ("enemies focus fire the weakest PC") without compute explosion. Multi-plan expectimax flagged as CP6 upgrade.

**Decided:** CP5.1 Pass 2, confirmed despite agent proposing heuristic-only for simplicity.

## D17: Initiative from seeded Perception roll

**Decision:** Initiative computed from Perception + d20 with seed for reproducibility. Fixed per scenario. Scenario file can override with explicit ordering.

**Rationale:** Standard PF2e rule. Seeded for deterministic tests. Explicit override for specific-scenario testing.

**Decided:** CP5.1 Pass 2.

## D18: Effects catalog deferred to Phase B+

**Decision:** Hard-code feat effects directly in Python (`has_plant_banner`, `has_deceptive_tactics`, etc.) for CP5-CP9. Build structured effects catalog in Phase B+ after simulator is validated.

**Rationale:** Rules coverage needed for CP5.1 is ~20 specific things. Building a general effects system now is premature abstraction. Hard-coding is fast, clear, easy to iterate on. Phase B+ extracts to structured catalog when we're ready to accept arbitrary imported characters.

**Decided:** CP5.1 Pass 2 and post-CP9 roadmap discussion.

## D19: characters/ directory as canonical storage

**Decision:** Character JSONs live in `characters/` in the repo. Same directory serves as eventual landing zone for Pathbuilder imports.

**Rationale:** Forward compatibility with Phase B importer. Clean progression from "our party data" to "any user's character."

**Decided:** Project setup (this conversation).

## D20: Claude Project + .claude/ dual setup

**Decision:** Migrate project to a dedicated Claude Project with structured Instructions and Knowledge files. Repo gets `CLAUDE.md` + `.claude/` directory with context and briefs.

**Rationale:** Context continuity across conversations. Instructions load baseline; Knowledge files are pulled on demand. CLI agent reads its own context from repo. Both audiences get the right information without duplication.

**Decided:** Project setup (this conversation).

## D21: RoundState as frozen snapshots

**Decision:** `RoundState`, `CombatantSnapshot`, `EnemySnapshot` are frozen dataclasses. Branching creates new instances via `dataclasses.replace()` with targeted dict updates. Underlying `Character` is shared.

**Rationale:** Enables cheap hybrid branching (dict copy + one frozen construction) without deep-copy overhead. Type system enforces "no accidental mutation across branches."

**Decided:** CP5.1.3b Pass 1; ratified Pass 2.

## D22: Kill/drop branching collapses to two worlds per target

**Decision:** For each action, crossing outcomes per-target are summed into P(event). If P(event) ≥ 5%, spawn exactly two child states: event-world (target HP=0) and no-event-world (non-crossing outcomes EV-folded). Multi-target spawns one branch per distinct alive/dead vector with ≥ 5% joint probability.

**Rationale:** Pass 1 original proposal branched per-outcome, producing redundant identical states. Two-world collapse preserves correctness while halving the tree.

**Decided:** CP5.1.3b Pass 2.

## D23: Reactions as full search-branching (C2)

**Decision:** Shield Block and Intercept Attack are first-class branching points in the search tree. Each eligible reaction creates a decision point expanding the triggering Strike's outcome set. Timing target: 15s per simulated round. Escape hatch: C1 commit-based if timing target missed.

**Rationale:** Treating reactions as automatic greedy policies throws away tactical value. Full branching captures "save Shield Block for the crit" decisions. Branching factor bounded by outcome-pruning threshold.

**Decided:** CP5.1.3b Pass 2.

## D24: Temp HP absorption not counted as damage_taken in scoring

**Decision:** Scoring's `damage_taken` component counts only real HP loss. Temp HP consumption is not reflected in the scoring penalty.

**Rationale:** Temp HP is a renewable resource (refreshes each round from Plant Banner). Counting consumption as "damage" would double-penalize.

**Decided:** CP5.1.3b Pass 2.

## Non-Decisions (deferred)

These came up but haven't been resolved. Revisit when relevant:

- **Support-role multiplier hardcoding:** Dalai is flagged as "support" via hardcoded name check. Ugly but pragmatic for CP5.1. Refactor in CP6 to a `role_weight` field on `Character`.
- **Enemy AI cooperation:** Multi-enemy coordination (flanking, spread-damage) emerges from single-best-response sometimes but isn't explicitly modeled. CP6 upgrade candidate.
- **Reaction policy optimality:** Intercept and Shield Block use greedy heuristics ("use if expected damage > threshold"). Optimal timing requires full-round reaction optimization. CP6 upgrade.
- **TypeScript port for web app:** Currently Python. Could port to TypeScript for unified stack if web app needs it. Defer decision to Phase D.
- **Monetization model:** One-time purchase $10-20 tentatively. Could consider subscription for effects catalog updates. Defer to post-CP9.
