"""
Item type code (3-letter) to display name mapping for D2/D2R.
"""
from __future__ import annotations

# Item code (3 chars) -> display name. Built from Misc, Weapons, Armor txt files.
ITEM_NAMES: dict[str, str] = {
    # Misc - potions, scrolls, gems, runes, keys, etc.
    "elx": "Elixir", "hpo": "Healing Potion", "mpo": "Mana Potion", "hpf": "Full Healing Potion",
    "mpf": "Full Mana Potion", "vps": "Stamina Potion", "yps": "Antidote Potion", "rvs": "Rejuv Potion",
    "rvl": "Full Rejuv Potion", "wms": "Thawing Potion", "tbk": "Town Portal Book", "ibk": "Identify Book",
    "amu": "Amulet", "vip": "Viper Amulet", "rin": "Ring", "gld": "Gold", "bks": "Bark Scroll",
    "bkd": "Deciphered Bark Scroll", "aqv": "Arrows", "tch": "Torch", "cqv": "Bolts", "tsc": "Town Portal Scroll",
    "isc": "Identify Scroll", "key": "Skeleton Key", "luv": "Mephisto Key", "ear": "Player Ear",
    "box": "Horadric Cube", "ass": "Book of Skill", "qey": "KhalimEye", "qhr": "KhalimHeart", "qbr": "KhalimBrain",
    "gcv": "Chipped Amethyst", "gfv": "Flawed Amethyst", "gsv": "Amethyst", "gzv": "Flawless Amethyst", "gpv": "Perfect Amethyst",
    "gcy": "Chipped Topaz", "gfy": "Flawed Topaz", "gsy": "Topaz", "gly": "Flawless Topaz", "gpy": "Perfect Topaz",
    "gcb": "Chipped Sapphire", "gfb": "Flawed Sapphire", "gsb": "Sapphire", "glb": "Flawless Sapphire", "gpb": "Perfect Sapphire",
    "gcg": "Chipped Emerald", "gfg": "Flawed Emerald", "gsg": "Emerald", "glg": "Flawless Emerald", "gpg": "Perfect Emerald",
    "gcr": "Chipped Ruby", "gfr": "Flawed Ruby", "gsr": "Ruby", "glr": "Flawless Ruby", "gpr": "Perfect Ruby",
    "gcw": "Chipped Diamond", "gfw": "Flawed Diamond", "gsw": "Diamond", "glw": "Flawless Diamond", "gpw": "Perfect Diamond",
    "hp1": "Lesser Healing Potion", "hp2": "Light Healing Potion", "hp3": "Healing Potion", "hp4": "Strong Healing Potion", "hp5": "Greater Healing Potion",
    "mp1": "Lesser Mana Potion", "mp2": "Light Mana Potion", "mp3": "Mana Potion", "mp4": "Strong Mana Potion", "mp5": "Greater Mana Potion",
    "skc": "Chipped Skull", "skf": "Flawed Skull", "sku": "Skull", "skl": "Flawless Skull", "skz": "Perfect Skull",
    "cm1": "Small Charm", "cm2": "Medium Charm", "cm3": "Large Charm", "rps": "Small Red Potion", "rpl": "Large Red Potion",
    "bps": "Small Blue Potion", "bpl": "Large Blue Potion", "jew": "Jewel", "toa": "Token of Absolution",
    "r01": "El Rune", "r02": "Eld Rune", "r03": "Tir Rune", "r04": "Nef Rune", "r05": "Eth Rune",
    "r06": "Ith Rune", "r07": "Tal Rune", "r08": "Ral Rune", "r09": "Ort Rune", "r10": "Thul Rune",
    "r11": "Amn Rune", "r12": "Sol Rune", "r13": "Shael Rune", "r14": "Dol Rune", "r15": "Hel Rune",
    "r16": "Io Rune", "r17": "Lum Rune", "r18": "Ko Rune", "r19": "Fal Rune", "r20": "Lem Rune",
    "r21": "Pul Rune", "r22": "Um Rune", "r23": "Mal Rune", "r24": "Ist Rune", "r25": "Gul Rune",
    "r26": "Vex Rune", "r27": "Ohm Rune", "r28": "Lo Rune", "r29": "Sur Rune", "r30": "Ber Rune",
    "r31": "Jah Rune", "r32": "Cham Rune", "r33": "Zod Rune", "pk1": "Pandemonium Key 1", "pk2": "Pandemonium Key 2", "pk3": "Pandemonium Key 3",
    # Weapons - axes, wands, swords, bows, etc.
    "hax": "Hand Axe", "axe": "Axe", "2ax": "Double Axe", "mpi": "Military Pick", "wax": "War Axe",
    "lax": "Large Axe", "bax": "Broad Axe", "btx": "Battle Axe", "gax": "Great Axe", "gix": "Giant Axe",
    "wnd": "Wand", "ywn": "Yew Wand", "bwn": "Bone Wand", "gwn": "Grim Wand", "clb": "Club", "scp": "Scepter",
    "gsc": "Grand Scepter", "wsp": "War Scepter", "spc": "Spiked Club", "mac": "Mace", "mst": "Morning Star",
    "fla": "Flail", "whm": "War Hammer", "mau": "Maul", "gma": "Great Maul", "ssd": "Short Sword",
    "scm": "Scimitar", "sbr": "Saber", "flc": "Falchion", "crs": "Crystal Sword", "bsd": "Broad Sword",
    "lsd": "Long Sword", "wsd": "War Sword", "2hs": "Two-Handed Sword", "clm": "Claymore", "gis": "Giant Sword",
    "bsw": "Bastard Sword", "flb": "Flamberge", "gsd": "Great Sword", "dgr": "Dagger", "dir": "Dirk",
    "kri": "Kriss", "bld": "Blade", "jav": "Javelin", "pil": "Pilum", "ssp": "Short Spear", "glv": "Glaive",
    "tsp": "Throwing Spear", "spr": "Spear", "tri": "Trident", "brn": "Brandistock", "spt": "Spetum",
    "pik": "Pike", "bar": "Bardiche", "vou": "Voulge", "scy": "Scythe", "pax": "Poleaxe", "hal": "Halberd",
    "wsc": "War Scythe", "sst": "Short Staff", "lst": "Long Staff", "cst": "Gnarled Staff", "bst": "Battle Staff",
    "wst": "War Staff", "sbw": "Short Bow", "hbw": "Hunter's Bow", "lbw": "Long Bow", "cbw": "Composite Bow",
    "sbb": "Short Battle Bow", "lbb": "Long Battle Bow", "swb": "Short War Bow", "lwb": "Long War Bow",
    "lxb": "Light Crossbow", "mxb": "Crossbow", "hxb": "Heavy Crossbow", "rxb": "Repeating Crossbow",
    "tkf": "Throwing Knife", "tax": "Throwing Axe", "bkf": "Balanced Knife", "bal": "Balanced Axe",
    "cap": "Cap", "skp": "Skull Cap", "hlm": "Helm", "fhl": "Full Helm", "ghm": "Great Helm",
    "crn": "Crown", "msk": "Mask", "qui": "Quilted Armor", "lea": "Leather Armor", "hla": "Hard Leather Armor",
    "stu": "Studded Leather", "rng": "Ring Mail", "scl": "Scale Mail", "chn": "Chain Mail", "brs": "Breast Plate",
    "spl": "Splint Mail", "plt": "Plate Mail", "fld": "Field Plate", "gth": "Gothic Plate", "ful": "Full Plate Mail",
    "aar": "Ancient Armor", "ltp": "Light Plate", "buc": "Buckler", "sml": "Small Shield", "lrg": "Large Shield",
    "kit": "Kite Shield", "tow": "Tower Shield", "gts": "Gothic Shield", "lgl": "Leather Gloves",
    "vgl": "Heavy Gloves", "mgl": "Bracers", "tgl": "Light Gauntlets", "hgl": "Gauntlets",
    "lbt": "Leather Boots", "vbt": "Heavy Boots", "mbt": "Chain Boots", "tbt": "Light Plate Boots", "hbt": "Plate Boots",
    "lbl": "Sash", "vbl": "Light Belt", "mbl": "Belt", "tbl": "Heavy Belt", "hbl": "Girdle",
    "bhm": "Bone Helm", "bsh": "Bone Shield", "spk": "Spiked Shield", "xap": "War Hat", "xkp": "Sallet",
    "xlm": "Casque", "xhl": "Basinet", "xhm": "Winged Helm", "xrn": "Grand Crown", "xsk": "Death Mask",
    "xui": "Ghost Armor", "xea": "Serpentskin Armor", "xla": "Demonhide Armor", "xtu": "Trellised Armor",
    "xng": "Linked Mail", "xcl": "Tigulated Mail", "xhn": "Mesh Armor", "xrs": "Cuirass", "xpl": "Russet Armor",
    "xlt": "Templar Coat", "xld": "Sharktooth Armor", "xth": "Embossed Plate", "xul": "Chaos Armor",
    "xar": "Ornate Armor", "xtp": "Mage Plate", "xuc": "Defender", "xml": "Round Shield", "xrg": "Scutum",
    "xit": "Dragon Shield", "xow": "Pavise", "xts": "Ancient Shield", "xlg": "Demonhide Gloves", "xvg": "Sharkskin Gloves",
    "xmg": "Heavy Bracers", "xtg": "Battle Gauntlets", "xhg": "War Gauntlets", "xlb": "Demonhide Boots",
    "xvb": "Sharkskin Boots", "xmb": "Mesh Boots", "xtb": "Battle Boots", "xhb": "War Boots",
    "zlb": "Demonhide Sash", "zvb": "Sharkskin Belt", "zmb": "Mesh Belt", "ztb": "Battle Belt", "zhb": "War Belt",
    "uap": "Shako", "ukp": "Hydraskull", "ulm": "Armet", "uhl": "Giant Conch", "uhm": "Spired Helm",
    "urn": "Corona", "usk": "Demonhead", "uui": "Dusk Shroud", "uea": "Wyrmhide", "ula": "Scarab Husk",
    "utu": "Wire Fleece", "ung": "Diamond Mail", "ucl": "Loricated Mail", "uhn": "Boneweave",
    "urs": "Great Hauberk", "upl": "Balrog Skin", "ult": "Hellforged Plate", "uld": "Kraken Shell",
    "uth": "Lacquered Plate", "uul": "Shadow Plate", "uar": "Sacred Armor", "utp": "Archon Plate",
    "uuc": "Heater", "uml": "Luna", "urg": "Hyperion", "uit": "Monarch", "uow": "Aegis", "uts": "Ward",
    "ulg": "Bramble Mitts", "uvg": "Vampirebone Gloves", "umg": "Vambraces", "utg": "Crusader Gauntlets",
    "uhg": "Ogre Gauntlets", "ulb": "Wyrmhide Boots", "uvb": "Scarabshell Boots", "umb": "Boneweave Boots",
    "utb": "Mirrored Boots", "uhb": "Myrmidon Greaves", "ulc": "Spiderweb Sash", "uvc": "Vampirefang Belt",
    "umc": "Mithril Coil", "utc": "Troll Belt", "uhc": "Colossus Girdle",     "ci0": "Circlet",
    "ci1": "Coronet", "ci2": "Tiara", "ci3": "Diadem",
}

# For advanced item skip: armor/weapon/stackable determine extra bit fields
ARMOR_CODES = frozenset(
    "cap skp hlm fhl ghm crn msk qui lea hla stu rng scl chn brs spl plt fld gth ful aar ltp "
    "buc sml lrg kit tow gts lgl vgl mgl tgl hgl lbt vbt mbt tbt hbt lbl vbl mbl tbl hbl "
    "bhm bsh spk xap xkp xlm xhl xhm xrn xsk xui xea xla xtu xng xcl xhn xrs xpl xlt xld xth xul "
    "xar xtp xuc xml xrg xit xow xts xlg xvg xmg xtg xhg xlb xvb xmb xtb xhb "
    "zlb zvb zmb ztb zhb uap ukp ulm uhl uhm urn usk uui uea ula utu ung ucl uhn urs upl ult uld "
    "uth uul uar utp uuc uml urg uit uow uts ulg uvg umg utg uhg ulb uvb umb utb uhb ulc uvc umc utc uhc ci0 ci1 ci2 ci3".split()
)
WEAPON_CODES = frozenset(
    "hax axe 2ax mpi wax lax bax btx gax gix wnd ywn bwn gwn clb scp gsc wsp spc mac mst fla whm mau gma "
    "ssd scm sbr flc crs bsd lsd wsd 2hs clm gis bsw flb gsd dgr dir kri bld jav pil ssp glv tsp spr tri brn spt "
    "pik bar vou scy pax hal wsc sst lst cst bst wst sbw hbw lbw cbw sbb lbb swb lwb lxb mxb hxb rxb tkf tax bkf bal".split()
)
STACKABLE_CODES = frozenset(
    "elx hpo mpo hpf mpf vps yps rvs rvl wms aqv cqv tsc isc hp1 hp2 hp3 hp4 hp5 mp1 mp2 mp3 mp4 mp5 "
    "rps rpl bps bpl r01 r02 r03 r04 r05 r06 r07 r08 r09 r10 r11 r12 r13 r14 r15 r16 r17 r18 r19 r20 "
    "r21 r22 r23 r24 r25 r26 r27 r28 r29 r30 r31 r32 r33 key pk1 pk2 pk3".split()
)


def is_armor(code: str) -> bool:
    return code.strip().lower()[:3] in ARMOR_CODES


def is_weapon(code: str) -> bool:
    return code.strip().lower()[:3] in WEAPON_CODES


def is_stackable(code: str) -> bool:
    return code.strip().lower()[:3] in STACKABLE_CODES


def get_item_name(type_code: str) -> str:
    """Return display name for item type code, or raw code if unknown."""
    if not type_code or len(type_code) < 3:
        return type_code or "???"
    code = type_code.strip().lower()[:3]
    return ITEM_NAMES.get(code, f"{code}")


# Location: parent (bit 58), equipped (bit 61), stash/panel (bit 73)
# parent: 0=stored, 1=equipped, 2=belt, 4=in transit, 6=socketed
# equipped: 1=head, 2=neck, 3=torso, 4=right hand, 5=left hand, 6=right ring, 7=left ring,
#           8=waist, 9=feet, 10=hands, 11=alt right, 12=alt left
# stash: 0=not here, 1=inventory, 4=cube, 5=stash
EQUIPPED_NAMES: dict[int, str] = {
    0: "-",
    1: "Head",
    2: "Neck",
    3: "Torso",
    4: "Right Hand",
    5: "Left Hand",
    6: "Right Ring",
    7: "Left Ring",
    8: "Waist",
    9: "Feet",
    10: "Hands",
    11: "Alt Right Hand",
    12: "Alt Left Hand",
}
PARENT_NAMES: dict[int, str] = {
    0: "Stored",
    1: "Equipped",
    2: "Belt",
    4: "In Transit",
    6: "Socketed",
}
STASH_NAMES: dict[int, str] = {
    0: "Not here",
    1: "Inventory",
    4: "Cube",
    5: "Stash",
}


def get_item_location(parent: int, equipped: int, stash: int, column: int = 0, row: int = 0) -> str:
    """Return human-readable location: 'Equipped: Head', 'Inventory c7,r2', etc."""
    if parent == 1 and equipped:
        slot = EQUIPPED_NAMES.get(equipped, f"Slot {equipped}")
        return f"Equipped: {slot}"
    if parent == 2:
        return "Belt"
    if parent == 4:
        return "In Transit"
    if parent == 6:
        return "Socketed"
    panel = STASH_NAMES.get(stash, f"Panel {stash}")
    if stash in (1, 4, 5):
        return f"{panel} c{column},r{row}"
    return panel
