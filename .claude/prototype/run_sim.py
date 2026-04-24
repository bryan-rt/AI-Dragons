"""
Main runner for PF2e tactical simulator.
Define your scenario, run the sim, get a ranked list of best tactic plays.
"""

from characters import (
    make_aetregan, make_rook, make_dalai, make_erisen,
    make_minion, make_brute,
)
from sim_engine import (
    parse_map, render_map, MortarState,
    best_mortar_target, mortar_total_expected_damage,
    expected_enemy_damage_to_party,
    tactic_strike_hard, tactic_gather_to_me,
    tactic_tactical_takedown, tactic_defensive_retreat,
    in_banner_aura, enemies_in_strike_reach, strike_against,
)


def run_scenario(grid_str: str, banner_pos: tuple,
                 enemy_setup: list = None, level: int = 1,
                 verbose: bool = True):
    """
    grid_str: ASCII map. Use:
        c = commander (Aetregan)
        g = guardian (Rook)
        b = bard (Dalai)
        i = inventor (Erisen)
        m = minion enemy
        M = brute enemy
        . = empty
    banner_pos: (row, col) for planted banner
    enemy_setup: optional list of dicts to override default enemies
    """
    positions = parse_map(grid_str)

    # Build party from positions (default level-1 stats)
    aetregan = make_aetregan(positions.get("c", (0, 0)))
    rook = make_rook(positions.get("g", (0, 0)))
    dalai = make_dalai(positions.get("b", (0, 0)))
    erisen = make_erisen(positions.get("i", (0, 0)))

    party = [aetregan, rook, dalai, erisen]

    # Build enemies from positions (m, m2, m3, ... and M, M2, ...)
    enemies = []
    for label, pos in positions.items():
        if label.startswith("m") and (len(label) == 1 or label[1].isdigit()):
            enemies.append(make_minion(pos, name=f"Minion-{label[1:] or '1'}"))
        elif label.startswith("M") and (len(label) == 1 or label[1].isdigit()):
            enemies.append(make_brute(pos, name=f"Brute-{label[1:] or '1'}"))

    if enemy_setup:
        enemies = enemy_setup

    all_chars = party + enemies

    if verbose:
        print("=" * 70)
        print("SCENARIO MAP")
        print("=" * 70)
        print(render_map(all_chars, banner_pos))
        print()
        print(f"Banner planted at: {banner_pos}")
        print()
        print("CHARACTERS:")
        for c in all_chars:
            in_aura = in_banner_aura(c, banner_pos) if c.role != "enemy" else "—"
            print(f"  {c.name:12s} ({c.role:8s}) HP {c.hp:>3}/{c.max_hp:<3} "
                  f"AC {c.ac}  Pos {c.pos}  In aura: {in_aura}")
        print()

    # Establish baseline: what does the round look like with NO commander tactic?
    baseline_party_dmg = compute_party_round_damage(party, enemies, all_chars,
                                                    banner_pos, mortar=None,
                                                    used_tactic=None)
    baseline_enemy_dmg = expected_enemy_damage_to_party(enemies, party)

    # Mortar setup: assume Erisen has it deployed and loaded at scenario start
    mortar = MortarState(deployed=True, aimed=False, loaded=True,
                         damage_dice_avg=7.0, save_dc=17)
    best_shot = best_mortar_target(mortar, all_chars)

    if verbose:
        print("=" * 70)
        print("MORTAR ANALYSIS")
        print("=" * 70)
        print(f"Best target square: {best_shot['target_pos']}")
        print(f"  Enemy damage: {best_shot['enemy_dmg']:.1f}")
        print(f"  Friendly damage: {best_shot['friendly_dmg']:.1f}")
        print(f"  Targets in burst:")
        for name, dmg, role in best_shot["targets_hit"]:
            tag = "ENEMY" if role == "enemy" else "ALLY ⚠"
            print(f"    {name:12s} ({tag}): ~{dmg:.1f} dmg")
        print(f"  Net damage: {best_shot['net_dmg']:.1f}")
        print()

    # Try each tactic
    if verbose:
        print("=" * 70)
        print("TACTIC OPTIONS")
        print("=" * 70)

    results = []

    # Strike Hard! options — try each squadmate
    for ally in [a for a in party if a is not aetregan and a.is_squadmate]:
        result = tactic_strike_hard(aetregan, ally, enemies, all_chars,
                                    banner_pos)
        result.name = f"Strike Hard! → {ally.name}"
        results.append(result)

    # Gather to Me! — paired with mortar shot
    if best_shot["target_pos"] and best_shot["enemy_dmg"] > 0:
        result = tactic_gather_to_me(aetregan, party, enemies, all_chars,
                                     banner_pos, mortar=mortar,
                                     mortar_target=best_shot["target_pos"])
        results.append(result)

    # Tactical Takedown
    result = tactic_tactical_takedown(aetregan, party, enemies, all_chars,
                                      banner_pos)
    results.append(result)

    # Defensive Retreat
    result = tactic_defensive_retreat(aetregan, party, enemies, all_chars,
                                      banner_pos)
    results.append(result)

    # Sort by net value (damage dealt - damage taken)
    results.sort(key=lambda r: r.net_value, reverse=True)

    if verbose:
        for i, r in enumerate(results, 1):
            print(f"\n[{i}] {r.name}  ({r.actions_used} action{'s' if r.actions_used != 1 else ''})")
            print(f"    {r.description}")
            print(f"    Damage dealt: {r.damage_dealt:.1f}")
            if r.damage_taken_estimate < 0:
                print(f"    Damage avoided: {-r.damage_taken_estimate:.1f}")
            elif r.damage_taken_estimate > 0:
                print(f"    Damage taken: {r.damage_taken_estimate:.1f}")
            print(f"    Net value: {r.net_value:+.1f}")
            for note in r.notes:
                print(f"    • {note}")

        print()
        print("=" * 70)
        print("BASELINE (no commander tactic)")
        print("=" * 70)
        print(f"Party expected damage to enemies (3 actions each): {baseline_party_dmg:.1f}")
        print(f"Enemy expected damage to party: {baseline_enemy_dmg:.1f}")
        print()
        print("=" * 70)
        print("RECOMMENDATION")
        print("=" * 70)
        if results:
            best = results[0]
            print(f"BEST PLAY: {best.name}  (+{best.net_value:.1f} net value)")
            print(f"  Reasoning: {best.description}")

    return {
        "best_mortar_shot": best_shot,
        "tactic_results": results,
        "baseline_enemy_dmg": baseline_enemy_dmg,
    }


def compute_party_round_damage(party, enemies, all_chars, banner_pos,
                               mortar=None, used_tactic=None):
    """Rough estimate of party output in 1 round if everyone plays normally."""
    total = 0
    for ally in party:
        if not enemies:
            continue
        # Assume 2 attacks if in melee range
        targets = enemies_in_strike_reach(ally, all_chars)
        if targets:
            best_target = max(targets, key=lambda e: strike_against(ally, e))
            total += strike_against(ally, best_target, map_penalty=0)
            total += strike_against(ally, best_target, map_penalty=5)
    return total


# ---------- DEMO SCENARIO ----------

if __name__ == "__main__":
    # Recreate the scenario from the conversation
    scenario_grid = """
    .  .  .  .  .  .  .  .  .  .
    .  .  m  .  .  .  .  .  .  .
    .  .  g  m  .  c  .  .  .  .
    .  .  .  .  .  .  .  .  .  .
    .  .  .  .  .  .  .  .  .  .
    .  .  .  .  b  .  .  .  .  .
    .  .  .  .  .  .  .  .  .  .
    .  .  .  .  i  .  .  .  .  .
    .  .  .  .  .  .  .  .  .  .
    .  .  .  .  .  .  .  .  .  .
    """
    banner_pos = (4, 5)  # E6 = row 4, col 5
    run_scenario(scenario_grid, banner_pos)
