# Characters

## Canonicity Rules

- **Aetregan** — Canonical from Pathbuilder JSON at `characters/aetregan.json`. Any discrepancy between code and JSON is a bug in code.
- **Rook, Dalai, Erisen** — Grounded defaults. May be reconciled with real Pathbuilder JSONs later if Bryan provides them. Documented as "subject to verification."

When Pathbuilder JSONs arrive for squadmates, a CP5.x mini-reconciliation corrects any discrepancies (following the CP4.5 pattern).

## Party Composition — Outlaws of Alkenstar, Level 1

### Aetregan (Commander) — PC
**Bryan's character.** Ancient Elf, Disciple of the Gear background.

Core stats:
- Stats: Str 10, Dex 16, Con 12, Int 18, Wis 12, Cha 10
- Key ability: Int
- Speed: 30 (Elf base)
- Max HP: 15 (Elf 6 + Commander 8 + Con +1)
- AC: 18 (Dex +3 + trained medium +3 + Subterfuge Suit +2)
- Class DC: 17 (Int +4 + trained +3)
- Perception: +6 (Wis +1 + expert +5)
- Fortitude: +4, Reflex: +8, Will: +6

Equipment:
- Weapon: Scorpion Whip (d4 slashing, finesse, reach, trip, disarm — lethal, no nonlethal trait)
- Armor: Inventor Subterfuge Suit (medium, +2 AC, no dex cap)
- Shield: Steel Shield (+2 AC when raised)
- Banner: worn on backpack (carried, not planted at L1)

Feats and features:
- **L1 Commander feat: Deceptive Tactics** ([AoN](https://2e.aonprd.com/Feats.aspx?ID=7794)) — substitute Warfare Lore for Deception in Create a Diversion / Feint checks
- **L1 Skill feat: Lengthy Diversion** — extends off-guard duration from Create a Diversion
- **L1 Heritage feat: Inventor Dedication** (via Ancient Elf Multitalented)
- **Awarded feats:** Shield Block, Quick Repair, Inventor, Lengthy Diversion
- **Ancestry feats:** Free Heart, Pickpocket
- **Class features:** Commander's Banner, Shields Up!, Mountaineering Training, Strike Hard!, Gather to Me!, Tactical Takedown, Drilled Reactions, Armor Innovation (Subterfuge)

Folio (5 tactics):
- Strike Hard!
- Gather to Me!
- Tactical Takedown
- Mountaineering Training
- Shields Up!

Prepared (3): Strike Hard!, Gather to Me!, Tactical Takedown.

Skill proficiencies (trained, per JSON):
- Acrobatics, Arcana, Crafting, Nature, Occultism, Religion, Society, Stealth, Survival, Thievery

Skill proficiencies (untrained):
- Athletics, Deception, Diplomacy, Intimidation, Medicine, Performance

Note: Deception is untrained, but Deceptive Tactics lets her use Warfare Lore (+7) in place of Deception for Create a Diversion and Feint.

Lores (trained):
- Warfare (+7 = Int +4 + trained proficiency +3 [rank bonus 2 + level 1])
- Deity (+7 = same)

Languages: Common, Dwarven, Elven, Necril, Osarian, Petran.

**Planned progression:**
- L2: Pick up Plant Banner feat (`has_plant_banner=True`, scenarios can use `planted=true`)

### Rook (Guardian) — Squadmate
Automaton Guardian. Tank.

Core stats (grounded defaults):
- Stats: Str 18, Dex 10, Con 16, Int 10, Wis 12, Cha 12
- Key ability: Str
- Speed: Base 25 (Automaton), effective 20 in full plate
- Max HP: 23 (Automaton 10 + Guardian 10 + Con +3)
- AC: 19 (Dex 0 capped + trained heavy +3 + Full Plate +6)
- Class DC: 17 (Str +4 + trained +3)
- Perception: +6 (Wis +1 + expert +5)
- Fortitude: +8, Reflex: +3, Will: +6
- Guardian reactions: 1

Equipment:
- Weapon: Longsword (d8 slashing, versatile_p)
- Armor: Full Plate (heavy, +6 AC, dex cap 0, -3 check, -10 speed)
- Shield: Steel Shield (+2 AC when raised)

Features:
- Shield Block
- Intercept Attack (Guardian reaction, redirects damage to self within 10 ft)
- Guardian's Armor (physical damage resistance 1 at L1, scaling +1/2 level)
- Ever Ready (Guardian reaction refresh, once per turn)

Skills (grounded defaults, trained):
- Athletics (+7 = Str +4 + trained proficiency +3 [rank bonus 2 + level 1])
- Intimidation, Society, Crafting

### Dalai Alpaca (Bard) — Squadmate
Human, Warrior Muse, worshipper of Shelyn.

Core stats (grounded defaults):
- Stats: Str 10, Dex 14, Con 12, Int 14, Wis 10, Cha 18
- Key ability: Cha
- Speed: 25 (Human)
- Max HP: 17 (Human 8 + Bard 8 + Con +1)
- AC: 16 (Dex +2 + trained light +3 + Leather +1)
- Class DC: 17 (Cha +4 + trained +3)
- Perception: +6 (Wis 0 + expert +5)
- Fortitude: +4, Reflex: +5, Will: +5

Equipment:
- Weapon: Rapier (d6 piercing, finesse, deadly d8, disarm)
- Armor: Leather Armor (light, +1 AC, dex cap 4)

Features:
- Courageous Anthem composition (+1 attack/+1 damage to allies in aura)
- Inspire Defense composition (CP5.2)
- Soothe spell (healing, CP5.2)
- Warrior Muse features

Skills (grounded defaults, trained):
- Occultism, Performance, Diplomacy, Intimidation, Athletics, Acrobatics

Lores (trained):
- Bardic, Warfare

**Role note:** Dalai is the party's support. Her Anthem buffs matter. CP5.1 scoring uses `role_multiplier=2` on her drop_cost because losing Anthem mid-round reduces party offensive output significantly.

### Erisen (Inventor) — Squadmate
Elf (with Nimble Elf heritage feat), Munitions Master.

Core stats (grounded defaults):
- Stats: Str 10, Dex 14, Con 14, Int 18, Wis 10, Cha 12
- Key ability: Int
- Speed: 35 (Elf 30 + Nimble Elf +5)
- Max HP: 16 (Elf 6 + Inventor 8 + Con +2)
- AC: 17 (Dex +2 capped +3 + trained medium +3 + Studded Leather +2)
- Class DC: 17 (Int +4 + trained +3)
- Perception: +3 (Wis 0 + trained +3)
- Fortitude: +7, Reflex: +7, Will: +3

Equipment:
- Weapon: Dagger (d4 piercing, agile, finesse, thrown_10, versatile_s)
- Armor: Studded Leather (medium, +2 AC, dex cap 3)

Features:
- Light Mortar siege weapon innovation (2d6 bludgeoning, DC = class DC, 10-ft burst, 120-ft range)
- Overdrive (Inventor feature, CP5.2)
- Armor innovation patterns

Skills (grounded defaults):
- Crafting: Trained (will be Expert via Inventor class progression; tracked as trained for L1)
- Arcana, Society, Athletics, Nature: Trained

Lores (trained):
- Engineering, Alkenstar

## Enemies

No canonical enemies yet — encountered in scenarios as needed. The `checkpoint_1_strike_hard.scenario` has Bandit1 as an example:
- AC 15, Reflex +5, Fortitude +3, Will +2
- Attack +7, damage 1d8+3, 2 attacks per turn
- Default max HP 20 (plausible L1 bandit)

Future scenarios (CP9 Outlaws of Alkenstar) will have real stat blocks.

## Character Data Storage

- `characters/aetregan.json` — Pathbuilder JSON export (authoritative for Aetregan)
- `characters/rook.json` — TBD; grounded defaults until reconciled
- `characters/dalai.json` — TBD; grounded defaults until reconciled
- `characters/erisen.json` — TBD; grounded defaults until reconciled

Code in `sim/party.py` is the source of truth for the simulator until Phase B imports land. At that point, `sim/party.py` becomes a fallback and `characters/*.json` is primary.
