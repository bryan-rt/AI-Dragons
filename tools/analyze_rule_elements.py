#!/usr/bin/env python3
"""Analyze Rule Elements in the session cache.

Run after initialize_session() to understand what Rule Element types
are present in the party's feats/spells and their combat relevance.

Usage:
    python tools/analyze_rule_elements.py [--cache PATH]

Output:
    Prints full markdown report to stdout.
    Saves report to tools/re_analysis_report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sim.catalog.session_cache import DEFAULT_CACHE_PATH, SessionCache

COMBAT_KINDS = {
    "FlatModifier", "AdjustModifier", "ActiveEffectLike",
    "Strike", "Aura", "SubstituteRoll", "Resistance",
}

UTILITY_KINDS = {
    "GrantItem", "ChoiceSet", "Note", "RollOption",
    "TokenLight", "TokenEffectIcon", "ItemAlteration", "CreatureSize",
}


def generate_report(cache: SessionCache) -> str:
    """Generate the full Rule Element analysis report as markdown."""
    items = cache.list_items()
    all_items_full = [cache.get_item(i["slug"]) for i in items]

    all_rules: list[dict] = []
    items_with_rules: list[dict] = []
    items_without_rules: list[dict] = []

    for item_data in all_items_full:
        if item_data is None:
            continue
        rules = json.loads(item_data["rule_elements"])
        if rules:
            items_with_rules.append(item_data)
            all_rules.extend(rules)
        else:
            items_without_rules.append(item_data)

    kind_counts = Counter(r.get("key", "unknown") for r in all_rules)
    total_rules = len(all_rules)
    total_items = len(items)

    lines: list[str] = []
    lines.append(f"# Rule Element Analysis — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("## Data Source")
    lines.append("Generated from local character JSONs (no network required).")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"- Total unique items cached: {total_items}")
    wr_pct = 100 * len(items_with_rules) // max(1, total_items)
    nr_pct = 100 * len(items_without_rules) // max(1, total_items)
    lines.append(f"- Items with Rule Elements: {len(items_with_rules)} ({wr_pct}%)")
    lines.append(f"- Items with no Rule Elements: {len(items_without_rules)} ({nr_pct}%)")
    lines.append(f"- Total Rule Elements: {total_rules}")
    lines.append(f"- Distinct Rule Element kinds: {len(kind_counts)}")
    lines.append("")

    # Kind distribution table
    lines.append("## Rule Element Kind Distribution")
    lines.append("")
    lines.append("| Kind | Count | % of Total | Classification |")
    lines.append("|---|---|---|---|")
    for kind, count in kind_counts.most_common():
        pct = f"{100 * count / max(1, total_rules):.1f}%"
        if kind in COMBAT_KINDS:
            cls = "COMBAT"
        elif kind in UTILITY_KINDS:
            cls = "CREATION-TIME/UTILITY"
        else:
            cls = "UNKNOWN"
        lines.append(f"| {kind} | {count} | {pct} | {cls} |")
    lines.append("")

    # Combat relevance totals
    combat_count = sum(c for k, c in kind_counts.items() if k in COMBAT_KINDS)
    utility_count = sum(c for k, c in kind_counts.items() if k in UTILITY_KINDS)
    unknown_count = total_rules - combat_count - utility_count

    lines.append("## Combat Relevance Summary")
    lines.append("")
    lines.append("| Category | Count | % of Total |")
    lines.append("|---|---|---|")
    lines.append(f"| COMBAT (need handlers in B+.3) | {combat_count} | "
                 f"{100 * combat_count / max(1, total_rules):.1f}% |")
    lines.append(f"| CREATION-TIME/UTILITY (no handlers needed) | {utility_count} | "
                 f"{100 * utility_count / max(1, total_rules):.1f}% |")
    if unknown_count:
        lines.append(f"| UNKNOWN (needs classification) | {unknown_count} | "
                     f"{100 * unknown_count / max(1, total_rules):.1f}% |")
    lines.append("")

    # Items with rules — detail
    lines.append("## Items With Rule Elements (Detail)")
    lines.append("")
    lines.append("| Item | Type | Rules | Kinds |")
    lines.append("|---|---|---|---|")
    for item in sorted(items_with_rules, key=lambda x: x["name"]):
        rules = json.loads(item["rule_elements"])
        kinds = ", ".join(sorted({r.get("key", "?") for r in rules}))
        lines.append(f"| {item['name']} | {item['item_type']} | "
                     f"{item['rule_count']} | {kinds} |")
    lines.append("")

    # Items without rules
    lines.append("## Items With No Rule Elements")
    lines.append("")
    lines.append("These items are text descriptions only and need no handlers.")
    lines.append("")
    for item in sorted(items_without_rules, key=lambda x: x["name"]):
        lines.append(f"- {item['name']} ({item['item_type']})")
    lines.append("")

    # Handler priority
    lines.append("## Recommended Handler Priority for B+.3")
    lines.append("")
    lines.append("Based on combat-relevant Rule Element frequency:")
    lines.append("")
    lines.append("| Priority | Kind | Count | Cumulative Coverage |")
    lines.append("|---|---|---|---|")
    priority = 1
    cumulative = 0
    for kind, count in kind_counts.most_common():
        if kind in COMBAT_KINDS:
            cumulative += count
            cum_pct = f"{100 * cumulative / max(1, combat_count):.0f}%"
            lines.append(f"| {priority} | {kind} | {count} | {cum_pct} |")
            priority += 1
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Rule Elements in session cache",
    )
    parser.add_argument(
        "--cache", default=DEFAULT_CACHE_PATH,
        help="Path to session cache SQLite file",
    )
    args = parser.parse_args()

    with SessionCache(args.cache) as cache:
        if not cache.list_items():
            print("Cache is empty. Run --init-session first.", file=sys.stderr)
            sys.exit(1)
        report = generate_report(cache)

    print(report)

    output_path = Path("tools/re_analysis_report.md")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
