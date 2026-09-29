"""
Finding, decoding and reading a No Man's Sky save.

Everything here is read-only. No function in this file opens a save for writing.

The save is a chain of LZ4 blocks, each with a 16-byte header, holding one JSON
document whose keys are obfuscated (VoxelX is "dZj", and so on). Rather than ship
a key mapping that would go stale with the next game update, this reads the file
structurally: a galactic address is the object with five numbers in it, a
teleporter endpoint is the object holding one of those plus a known type string.
That has survived several game versions unchanged.
"""
import json
import os
import platform
import re
import struct
import sys
from pathlib import Path

import lz4_block

MAGIC = 0xFEEDA1E5
NMS_STEAM_APPID = "275850"
LY_PER_VOXEL = 400

# The game's own galaxy order, zero-indexed to match RealityIndex: index 0 is
# galaxy 1, Euclid. Cross-checked against two independent published lists, whose
# first ten agreed with the values this project had already verified in-game.
# Index 255 (Odyalutai) exists in the data but is not reachable in normal play.
GALAXIES = {
    0: "Euclid", 1: "Hilbert Dimension", 2: "Calypso", 3: "Hesperius Dimension",
    4: "Hyades", 5: "Ickjamatew", 6: "Budullangr", 7: "Kikolgallr",
    8: "Eltiensleen", 9: "Eissentam", 10: "Elkupalos", 11: "Aptarkaba",
    12: "Ontiniangp", 13: "Odiwagiri", 14: "Ogtialabi", 15: "Muhacksonto",
    16: "Hitonskyer", 17: "Rerasmutul", 18: "Isdoraijung", 19: "Doctinawyra",
    20: "Loychazinq", 21: "Zukasizawa", 22: "Ekwathore", 23: "Yeberhahne",
    24: "Twerbetek", 25: "Sivarates", 26: "Eajerandal", 27: "Aldukesci",
    28: "Wotyarogii", 29: "Sudzerbal", 30: "Maupenzhay", 31: "Sugueziume",
    32: "Brogoweldian", 33: "Ehbogdenbu", 34: "Ijsenufryos", 35: "Nipikulha",
    36: "Autsurabin", 37: "Lusontrygiamh", 38: "Rewmanawa", 39: "Ethiophodhe",
    40: "Urastrykle", 41: "Xobeurindj", 42: "Oniijialdu", 43: "Wucetosucc",
    44: "Ebyeloof", 45: "Odyavanta", 46: "Milekistri", 47: "Waferganh",
    48: "Agnusopwit", 49: "Teyaypilny", 50: "Zalienkosm", 51: "Ladgudiraf",
    52: "Mushonponte", 53: "Amsentisz", 54: "Fladiselm", 55: "Laanawemb",
    56: "Ilkerloor", 57: "Davanossi", 58: "Ploehrliou", 59: "Corpinyaya",
    60: "Leckandmeram", 61: "Quulngais", 62: "Nokokipsechl", 63: "Rinblodesa",
    64: "Loydporpen", 65: "Ibtrevskip", 66: "Elkowaldb", 67: "Heholhofsko",
    68: "Yebrilowisod", 69: "Husalvangewi", 70: "Ovna'uesed", 71: "Bahibusey",
    72: "Nuybeliaure", 73: "Doshawchuc", 74: "Ruckinarkh", 75: "Thorettac",
    76: "Nuponoparau", 77: "Moglaschil", 78: "Uiweupose", 79: "Nasmilete",
    80: "Ekdaluskin", 81: "Hakapanasy", 82: "Dimonimba", 83: "Cajaccari",
    84: "Olonerovo", 85: "Umlanswick", 86: "Henayliszm", 87: "Utzenmate",
    88: "Umirpaiya", 89: "Paholiang", 90: "Iaereznika", 91: "Yudukagath",
    92: "Boealalosnj", 93: "Yaevarcko", 94: "Coellosipp", 95: "Wayndohalou",
    96: "Smoduraykl", 97: "Apmaneessu", 98: "Hicanpaav", 99: "Akvasanta",
    100: "Tuychelisaor", 101: "Rivskimbe", 102: "Daksanquix", 103: "Kissonlin",
    104: "Aediabiel", 105: "Ulosaginyik", 106: "Roclaytonycar", 107: "Kichiaroa",
    108: "Irceauffey", 109: "Nudquathsenfe", 110: "Getaizakaal", 111: "Hansolmien",
    112: "Bloytisagra", 113: "Ladsenlay", 114: "Luyugoslasr", 115: "Ubredhatk",
    116: "Cidoniana", 117: "Jasinessa", 118: "Torweierf", 119: "Saffneckm",
    120: "Thnistner", 121: "Dotusingg", 122: "Luleukous", 123: "Jelmandan",
    124: "Otimanaso", 125: "Enjaxusanto", 126: "Sezviktorew", 127: "Zikehpm",
    128: "Bephembah", 129: "Broomerrai", 130: "Meximicka", 131: "Venessika",
    132: "Gaiteseling", 133: "Zosakasiro", 134: "Drajayanes", 135: "Ooibekuar",
    136: "Urckiansi", 137: "Dozivadido", 138: "Emiekereks", 139: "Meykinunukur",
    140: "Kimycuristh", 141: "Roansfien", 142: "Isgarmeso", 143: "Daitibeli",
    144: "Gucuttarik", 145: "Enlaythie", 146: "Drewweste", 147: "Akbulkabi",
    148: "Homskiw", 149: "Zavainlani", 150: "Jewijkmas", 151: "Itlhotagra",
    152: "Podalicess", 153: "Hiviusauer", 154: "Halsebenk", 155: "Puikitoac",
    156: "Gaybakuaria", 157: "Grbodubhe", 158: "Rycempler", 159: "Indjalala",
    160: "Fontenikk", 161: "Pasycihelwhee", 162: "Ikbaksmit", 163: "Telicianses",
    164: "Oyleyzhan", 165: "Uagerosat", 166: "Impoxectin", 167: "Twoodmand",
    168: "Hilfsesorbs", 169: "Ezdaranit", 170: "Wiensanshe", 171: "Ewheelonc",
    172: "Litzmantufa", 173: "Emarmatosi", 174: "Mufimbomacvi", 175: "Wongquarum",
    176: "Hapirajua", 177: "Igbinduina", 178: "Wepaitvas", 179: "Sthatigudi",
    180: "Yekathsebehn", 181: "Ebedeagurst", 182: "Nolisonia", 183: "Ulexovitab",
    184: "Iodhinxois", 185: "Irroswitzs", 186: "Bifredait", 187: "Beiraghedwe",
    188: "Yeonatlak", 189: "Cugnatachh", 190: "Nozoryenki", 191: "Ebralduri",
    192: "Evcickcandj", 193: "Ziybosswin", 194: "Heperclait", 195: "Sugiuniam",
    196: "Aaseertush", 197: "Uglyestemaa", 198: "Horeroedsh", 199: "Drundemiso",
    200: "Ityanianat", 201: "Purneyrine", 202: "Dokiessmat", 203: "Nupiacheh",
    204: "Dihewsonj", 205: "Rudrailhik", 206: "Tweretnort", 207: "Snatreetze",
    208: "Iwundaracos", 209: "Digarlewena", 210: "Erquagsta", 211: "Logovoloin",
    212: "Boyaghosganh", 213: "Kuolungau", 214: "Pehneldept", 215: "Yevettiiqidcon",
    216: "Sahliacabru", 217: "Noggalterpor", 218: "Chmageaki", 219: "Veticueca",
    220: "Vittesbursul", 221: "Nootanore", 222: "Innebdjerah", 223: "Kisvarcini",
    224: "Cuzcogipper", 225: "Pamanhermonsu", 226: "Brotoghek", 227: "Mibittara",
    228: "Huruahili", 229: "Raldwicarn", 230: "Ezdartlic", 231: "Badesclema",
    232: "Isenkeyan", 233: "Iadoitesu", 234: "Yagrovoisi", 235: "Ewcomechio",
    236: "Inunnunnoda", 237: "Dischiutun", 238: "Yuwarugha", 239: "Ialmendra",
    240: "Reponudrle", 241: "Rinjanagrbo", 242: "Zeziceloh", 243: "Oeileutasc",
    244: "Zicniijinis", 245: "Dugnowarilda", 246: "Neuxoisan", 247: "Ilmenhorn",
    248: "Rukwatsuku", 249: "Nepitzaspru", 250: "Chcehoemig", 251: "Haffneyrin",
    252: "Uliciawai", 253: "Tuhgrespod", 254: "Iousongola", 255: "Odyalutai",
}

TELEPORTER_KINDS = {
    "Spacestation", "SpacestationFixPosition", "Base", "ExternalBase",
    "Settlement", "Freighter", "Nexus", "Alliance",
}

# A station, settlement or base is named after the system it sits in, so it can
# identify where you are standing. A freighter travels with you and never can.
PLACE_RANK = {"Spacestation": 0, "Settlement": 1, "Base": 2, "ExternalBase": 3}


# --------------------------------------------------------------------------
# Locating the save
# --------------------------------------------------------------------------

def _steam_roots():
    """Every Steam install directory worth checking, on any platform."""
    home = Path.home()
    roots = [
        home / ".steam" / "steam",              # Linux, traditional
        home / ".steam" / "root",
        home / ".local" / "share" / "Steam",    # Linux + Steam Deck
        home / "Library" / "Application Support" / "Steam",   # macOS
        Path("C:/Program Files (x86)/Steam"),   # Windows default
        Path("C:/Program Files/Steam"),
    ]
    if os.environ.get("PROGRAMFILES(X86)"):
        roots.append(Path(os.environ["PROGRAMFILES(X86)"]) / "Steam")
    return [r for r in roots if r.is_dir()]


def _steam_libraries():
    """Steam can spread games over several drives; libraryfolders.vdf lists them.

    Parsed with a regex rather than a real VDF parser: the only thing needed is
    the "path" values, and a malformed file should degrade to "found nothing"
    instead of raising.
    """
    libs = []
    for root in _steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s*"([^"]+)"', text):
            libs.append(Path(match.group(1).replace("\\\\", "/")))
    return libs


def _proton_prefixes():
    """Windows-inside-Linux save locations, for Proton and Steam Deck."""
    out = []
    for lib in _steam_libraries():
        pfx = (lib / "steamapps" / "compatdata" / NMS_STEAM_APPID / "pfx" /
               "drive_c" / "users" / "steamuser")
        if pfx.is_dir():
            # Newer prefixes use AppData/Roaming; older ones have an
            # "Application Data" symlink pointing at it. Try both.
            out.append(pfx / "AppData" / "Roaming")
            out.append(pfx / "Application Data")
    return out


def _native_appdata():
    """Where the game puts saves when it is not running under Proton."""
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        return [Path(appdata)] if appdata else [home / "AppData" / "Roaming"]
    if system == "Darwin":
        return [home / "Library" / "Application Support"]
    return []


def candidate_dirs():
    """Every directory that might hold NMS saves, most likely first."""
    seen, out = set(), []
    for base in _native_appdata() + _proton_prefixes():
        nms = base / "HelloGames" / "NMS"
        if not nms.is_dir():
            continue
        # Each Steam or GOG account gets its own subdirectory (st_<id>, DefaultUser).
        for child in sorted(nms.iterdir()):
            if not child.is_dir():
                continue
            try:
                real = child.resolve()
            except OSError:
                real = child
            if real in seen:
                continue
            seen.add(real)
            out.append(child)
    return out


def find_saves():
    """All save files found on this machine, newest first.

    Excludes the mf_*.hg metadata files, which are a few hundred bytes of
    bookkeeping rather than a save.
    """
    saves = []
    for d in candidate_dirs():
        for f in d.glob("save*.hg"):
            if not f.name.startswith("mf_"):
                saves.append(f)
    return sorted(saves, key=lambda p: p.stat().st_mtime, reverse=True)


def newest_save(explicit=None):
    """The save to read: an explicit path if given, otherwise the most recent."""
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_dir():
            here = sorted((f for f in p.glob("save*.hg")
                           if not f.name.startswith("mf_")),
                          key=lambda x: x.stat().st_mtime, reverse=True)
            if not here:
                raise FileNotFoundError(f"No save*.hg files in {p}")
            return here[0]
        if not p.is_file():
            raise FileNotFoundError(f"No such save file: {p}")
        return p

    saves = find_saves()
    if not saves:
        raise FileNotFoundError(
            "Could not find a No Man's Sky save automatically.\n"
            "Pass the path yourself:  python3 core_run.py --save "
            "/path/to/save.hg\n"
            "The README lists the usual location on each platform.")
    return saves[0]


# --------------------------------------------------------------------------
# Reading it
# --------------------------------------------------------------------------

def decompress(path):
    """Inflate a .hg save into its JSON tree. Opens the file read-only."""
    data = Path(path).read_bytes()
    out, off = bytearray(), 0
    while off + 16 <= len(data):
        magic, csize, dsize, _ = struct.unpack_from("<IIII", data, off)
        if magic != MAGIC:
            break
        off += 16
        if csize == 0 or off + csize > len(data):
            break
        out += lz4_block.decompress(data[off:off + csize], dsize)
        off += csize
    if not out:
        raise ValueError(
            f"{Path(path).name} does not look like a No Man's Sky save "
            "(no LZ4 blocks found). Use save.hg or save2.hg, not accountdata.hg.")
    text = bytes(out).rstrip(b"\x00").decode("utf-8", errors="replace")
    return json.loads(text)


def _is_galactic_address(node):
    return (isinstance(node, dict) and len(node) == 5
            and all(isinstance(v, int) for v in node.values()))


def _is_universe_address(node):
    if not isinstance(node, dict) or len(node) != 2:
        return False
    vals = list(node.values())
    return (any(isinstance(v, int) for v in vals)
            and any(_is_galactic_address(v) for v in vals))


def _read_universe_address(node):
    """Pull galaxy index and voxel coordinates out of a UniverseAddress."""
    vals = list(node.values())
    galaxy = next(v for v in vals if isinstance(v, int))
    ga = next(v for v in vals if _is_galactic_address(v))
    x, y, z, system = list(ga.values())[:4]
    return {"galaxy": galaxy, "x": x, "y": y, "z": z, "system_index": system}


def _is_endpoint(node):
    if not isinstance(node, dict):
        return False
    vals = list(node.values())
    return (any(_is_universe_address(v) for v in vals)
            and any(isinstance(v, str) and v in TELEPORTER_KINDS for v in vals))


def _find_endpoint_list(root):
    """Depth-first hunt for the TeleportEndpoints array."""
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            if node and _is_endpoint(node[0]):
                return node
            stack.extend(reversed(node))
        elif isinstance(node, dict):
            stack.extend(reversed(list(node.values())))
    return None


def _find_position(root, endpoint_list):
    """The player's own address lives on the object that holds the endpoint list."""
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if any(v is endpoint_list for v in node.values()):
                for v in node.values():
                    if _is_universe_address(v):
                        return _read_universe_address(v)
                return None
            stack.extend(reversed(list(node.values())))
        elif isinstance(node, list):
            stack.extend(reversed(node))
    return None


def distance_ly(addr):
    """Light years from the galactic core. Voxel coordinates are galaxy-local,
    so this is correct in any galaxy."""
    d = (addr["x"] ** 2 + addr["y"] ** 2 + addr["z"] ** 2) ** 0.5
    return round(d * LY_PER_VOXEL)


def galaxy_name(index):
    return GALAXIES.get(index, f"Galaxy {index}")


def build_payload(save_path):
    """Read a save and return the ranking, ready to hand to the page."""
    root = decompress(save_path)

    endpoint_list = _find_endpoint_list(root)
    if endpoint_list is None:
        raise ValueError("Could not find the teleporter list in this save. "
                         "The format may have changed in a game update.")

    here = _find_position(root, endpoint_list)
    if here is None:
        raise ValueError("Found the teleporter list but not your current position.")

    seen, endpoints = set(), []
    for entry in endpoint_list:
        vals = list(entry.values())
        addr_node = next((v for v in vals if _is_universe_address(v)), None)
        if addr_node is None:
            continue
        addr = _read_universe_address(addr_node)
        kind = next((v for v in vals
                     if isinstance(v, str) and v in TELEPORTER_KINDS), "Unknown")
        name = next((v for v in vals
                     if isinstance(v, str) and v not in TELEPORTER_KINDS), "(unnamed)")

        # One station can be stored twice, as Spacestation and as
        # SpacestationFixPosition. Collapse those into a single destination.
        key = (addr["galaxy"], addr["x"], addr["y"], addr["z"],
               addr["system_index"], name)
        if key in seen:
            continue
        seen.add(key)

        endpoints.append({
            "d": distance_ly(addr), "n": name,
            "k": kind.replace("FixPosition", ""),
            "g": addr["galaxy"], "gn": galaxy_name(addr["galaxy"]),
            "v": [addr["x"], addr["y"], addr["z"]], "s": addr["system_index"],
        })

    endpoints.sort(key=lambda e: e["d"])
    mtime = Path(save_path).stat().st_mtime

    return {
        "saveMs": int(mtime * 1000),
        "file": Path(save_path).name,
        "path": str(save_path),
        "auto": True,
        "here": {
            "distance_ly": distance_ly(here),
            "galaxy": here["galaxy"], "galaxy_name": galaxy_name(here["galaxy"]),
            "x": here["x"], "y": here["y"], "z": here["z"],
            "system_index": here["system_index"],
        },
        "eps": endpoints,
    }
