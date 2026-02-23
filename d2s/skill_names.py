"""
Skill ID to name mapping for D2/D2R. The 30 bytes in the save file correspond to
skill indices 0-29 within each class's skill set. skill_id = CLASS_SKILL_OFFSET[class] + index.
"""
from __future__ import annotations

# First skill ID for each class (save byte index 0 maps to this ID)
CLASS_SKILL_OFFSET: dict[int, int] = {
    0: 6,   # Amazon
    1: 36,  # Sorceress
    2: 66,  # Necromancer
    3: 96,  # Paladin
    4: 126, # Barbarian
    5: 221, # Druid
    6: 251, # Assassin
    7: 281, # Warlock (D2R Reign of the Warlock)
}

# Skill ID -> display name (from Skills.txt, player skills 0-310)
SKILL_NAMES: dict[int, str] = {
    0: "Attack", 1: "Kick", 2: "Throw", 3: "Unsummon", 4: "Left Hand Throw", 5: "Left Hand Swing",
    6: "Magic Arrow", 7: "Fire Arrow", 8: "Inner Sight", 9: "Critical Strike", 10: "Jab",
    11: "Cold Arrow", 12: "Multiple Shot", 13: "Dodge", 14: "Power Strike", 15: "Poison Javelin",
    16: "Exploding Arrow", 17: "Slow Missiles", 18: "Avoid", 19: "Impale", 20: "Lightning Bolt",
    21: "Ice Arrow", 22: "Guided Arrow", 23: "Penetrate", 24: "Charged Strike", 25: "Plague Javelin",
    26: "Strafe", 27: "Immolation Arrow", 28: "Dopplezon", 29: "Evade", 30: "Fend",
    31: "Freezing Arrow", 32: "Valkyrie", 33: "Pierce", 34: "Lightning Strike", 35: "Lightning Fury",
    36: "Fire Bolt", 37: "Warmth", 38: "Charged Bolt", 39: "Ice Bolt", 40: "Frozen Armor",
    41: "Inferno", 42: "Static Field", 43: "Telekinesis", 44: "Frost Nova", 45: "Ice Blast",
    46: "Blaze", 47: "Fire Ball", 48: "Nova", 49: "Lightning", 50: "Shiver Armor",
    51: "Fire Wall", 52: "Enchant", 53: "Chain Lightning", 54: "Teleport", 55: "Glacial Spike",
    56: "Meteor", 57: "Thunder Storm", 58: "Energy Shield", 59: "Blizzard", 60: "Chilling Armor",
    61: "Fire Mastery", 62: "Hydra", 63: "Lightning Mastery", 64: "Frozen Orb", 65: "Cold Mastery",
    66: "Amplify Damage", 67: "Teeth", 68: "Bone Armor", 69: "Skeleton Mastery", 70: "Raise Skeleton",
    71: "Dim Vision", 72: "Weaken", 73: "Poison Dagger", 74: "Corpse Explosion", 75: "Clay Golem",
    76: "Iron Maiden", 77: "Terror", 78: "Bone Wall", 79: "Golem Mastery", 80: "Raise Skeletal Mage",
    81: "Confuse", 82: "Life Tap", 83: "Poison Explosion", 84: "Bone Spear", 85: "BloodGolem",
    86: "Attract", 87: "Decrepify", 88: "Bone Prison", 89: "Summon Resist", 90: "IronGolem",
    91: "Lower Resist", 92: "Poison Nova", 93: "Bone Spirit", 94: "FireGolem", 95: "Revive",
    96: "Sacrifice", 97: "Smite", 98: "Might", 99: "Prayer", 100: "Resist Fire",
    101: "Holy Bolt", 102: "Holy Fire", 103: "Thorns", 104: "Defiance", 105: "Resist Cold",
    106: "Zeal", 107: "Charge", 108: "Blessed Aim", 109: "Cleansing", 110: "Resist Lightning",
    111: "Vengeance", 112: "Blessed Hammer", 113: "Concentration", 114: "Holy Freeze", 115: "Vigor",
    116: "Conversion", 117: "Holy Shield", 118: "Holy Shock", 119: "Sanctuary", 120: "Meditation",
    121: "Fist of the Heavens", 122: "Fanaticism", 123: "Conviction", 124: "Redemption", 125: "Salvation",
    126: "Bash", 127: "Sword Mastery", 128: "Axe Mastery", 129: "Mace Mastery", 130: "Howl",
    131: "Find Potion", 132: "Leap", 133: "Double Swing", 134: "Pole Arm Mastery", 135: "Throwing Mastery",
    136: "Spear Mastery", 137: "Taunt", 138: "Shout", 139: "Stun", 140: "Double Throw",
    141: "Increased Stamina", 142: "Find Item", 143: "Leap Attack", 144: "Concentrate", 145: "Iron Skin",
    146: "Battle Cry", 147: "Frenzy", 148: "Increased Speed", 149: "Battle Orders", 150: "Grim Ward",
    151: "Whirlwind", 152: "Berserk", 153: "Natural Resistance", 154: "War Cry", 155: "Battle Command",
    221: "Raven", 222: "Plague Poppy", 223: "Wearwolf", 224: "Shape Shifting", 225: "Firestorm",
    226: "Oak Sage", 227: "Summon Spirit Wolf", 228: "Wearbear", 229: "Molten Boulder", 230: "Arctic Blast",
    231: "Cycle of Life", 232: "Feral Rage", 233: "Maul", 234: "Eruption", 235: "Cyclone Armor",
    236: "Heart of Wolverine", 237: "Summon Fenris", 238: "Rabies", 239: "Fire Claws", 240: "Twister",
    241: "Vines", 242: "Hunger", 243: "Shock Wave", 244: "Volcano", 245: "Tornado",
    246: "Spirit of Barbs", 247: "Summon Grizzly", 248: "Fury", 249: "Armageddon", 250: "Hurricane",
    251: "Fire Trauma", 252: "Claw Mastery", 253: "Psychic Hammer", 254: "Tiger Strike", 255: "Dragon Talon",
    256: "Shock Field", 257: "Blade Sentinel", 258: "Quickness", 259: "Fists of Fire", 260: "Dragon Claw",
    261: "Charged Bolt Sentry", 262: "Wake of Fire Sentry", 263: "Weapon Block", 264: "Cloak of Shadows",
    265: "Cobra Strike", 266: "Blade Fury", 267: "Fade", 268: "Shadow Warrior", 269: "Claws of Thunder",
    270: "Dragon Tail", 271: "Lightning Sentry", 272: "Inferno Sentry", 273: "Mind Blast", 274: "Blades of Ice",
    275: "Dragon Flight", 276: "Death Sentry", 277: "Blade Shield", 278: "Venom", 279: "Shadow Master",
    280: "Royal Strike",
    # Warlock (D2R Reign of the Warlock) - IDs 281-310
    281: "Miasma Bolt", 282: "Miasma Chain", 283: "Abyss", 284: "Ring of Fire", 285: "Flame Wave",
    286: "Apocalypse", 287: "Sigil: Lethargy", 288: "Sigil: Rancor", 289: "Sigil: Death",
    290: "Enhanced Entropy", 291: "Levitation Mastery", 292: "Cleave", 293: "Echoing Strike",
    294: "Blade Warp", 295: "Hex: Bane", 296: "Hex: Purge", 297: "Psychic Ward",
    298: "Consume", 299: "Bind Demon", 300: "Blood Oath",
    301: "Warlock Skill 21", 302: "Warlock Skill 22", 303: "Warlock Skill 23",
    304: "Warlock Skill 24", 305: "Warlock Skill 25", 306: "Warlock Skill 26",
    307: "Warlock Skill 27", 308: "Warlock Skill 28", 309: "Warlock Skill 29",
    310: "Warlock Skill 30",
}

def get_skill_name(skill_id: int) -> str:
    """Return display name for a skill ID, or 'Unknown' if not found."""
    return SKILL_NAMES.get(skill_id, f"Skill {skill_id}")

def skill_id_for_slot(char_class: int | None, slot_index: int) -> int | None:
    """Get the global skill ID for a given class and slot (0-29). Returns None if class unknown."""
    if char_class is None or char_class not in CLASS_SKILL_OFFSET:
        return None
    return CLASS_SKILL_OFFSET[char_class] + slot_index
