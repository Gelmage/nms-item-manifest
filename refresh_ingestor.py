#!/usr/bin/env python3
"""Rebuild the Nutrient Ingestor data in nms_index.json from the installed game.

A food does two unrelated things. Eaten from the inventory it gives one effect;
loaded into a Nutrient Ingestor it gives a different stat entirely, for far
longer. The public data sources carry only the first -- bradhave94's extractor
exports FoodBonusStat as None for all 386 foods even though the game files have
it -- so this reads the second straight out of the game you have installed.

    python3 refresh_ingestor.py                      find the game automatically
    python3 refresh_ingestor.py --game /path/to/NMS  point at it explicitly
    python3 refresh_ingestor.py --check              report, write nothing

What comes from where:

    effect    GcProductTable -> FoodBonusStat (a GcStatsTypes enum)
    duration  BaseFoodDuration (600s, in GcGameplayGlobals) x CookingValue
    percent   NOT in the game files. FoodBonusStatAmount is 0.0 for all 2199
              products, so the game computes it at runtime. The numbers in
              ingestor_percent.json are a community listing, each one checked
              against the game files before it was kept.

Needs two tools, neither of which ships with this project:

    pip install hgpaktool                 unpacks the HGPAK .pak format (NMS 5.50+)
    MBINCompiler (linux build) + .NET 8   decodes .mbin -> .MXML
      https://github.com/monkeyman192/MBINCompiler/releases

Read-only with respect to the game: it copies out of the .pak and never writes
back.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TABLE = "metadata/reality/tables/nms_reality_gcproducttable.mbin"
PAK = "NMSARC.Precache.pak"
BASE_FOOD_DURATION = 600.0          # seconds, from GcGameplayGlobals

GAME_GUESSES = [
    "/nsm/SteamLibrary/steamapps/common/No Man's Sky",
    "~/.steam/debian-installation/steamapps/common/No Man's Sky",
    "~/.local/share/Steam/steamapps/common/No Man's Sky",
    "C:/Program Files (x86)/Steam/steamapps/common/No Man's Sky",
]


def find_game(explicit):
    for cand in ([explicit] if explicit else []) + GAME_GUESSES:
        if not cand:
            continue
        p = Path(cand).expanduser()
        if (p / "GAMEDATA" / "PCBANKS" / PAK).exists():
            return p
    return None


def need(tool, hint):
    if shutil.which(tool) is None and not Path(tool).exists():
        sys.exit(f"{tool} not found. {hint}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game")
    ap.add_argument("--mbincompiler", default="MBINCompiler")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    game = find_game(args.game)
    if not game:
        sys.exit("No Man's Sky not found. Pass --game /path/to/'No Man's Sky'.")
    print(f"game: {game}")

    need("hgpaktool", "Install it with: pip install hgpaktool")
    need(args.mbincompiler,
         "Download the linux build from "
         "https://github.com/monkeyman192/MBINCompiler/releases and pass "
         "--mbincompiler /path/to/MBINCompiler")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pak = game / "GAMEDATA" / "PCBANKS" / PAK
        subprocess.run(["hgpaktool", "-U", "-q", "-O", str(tmp), "-f", TABLE, str(pak)],
                       check=True)
        mbin = tmp / TABLE
        if not mbin.exists() or mbin.stat().st_size == 0:
            sys.exit(f"Could not extract {TABLE} from {pak.name}")
        subprocess.run([args.mbincompiler, "convert", str(mbin)], check=True)
        mxml = mbin.with_suffix(".MXML")
        if not mxml.exists():
            sys.exit("MBINCompiler produced no .MXML -- is .NET 8 installed?")
        text = mxml.read_text(encoding="utf-8", errors="replace")

    # Each product is "<Property name="Table" value="GcProductData" _id="ID">".
    parts = re.split(r'<Property name="Table" value="GcProductData" _id="([^"]*)">', text)
    found = {}
    for i in range(1, len(parts), 2):
        pid, body = parts[i], parts[i + 1]
        cv = re.search(r'<Property name="CookingValue" value="([\d.\-]+)"', body)
        stat = re.search(r'<Property name="FoodBonusStat" value="GcStatsTypes">\s*'
                         r'<Property name="StatsType" value="([^"]*)"', body)
        if not cv or not stat:
            continue
        cv, stat = float(cv.group(1)), stat.group(1)
        if stat == "Unspecified" or cv <= 0:
            continue
        found[pid] = (stat, round(BASE_FOOD_DURATION * cv))
    print(f"products with an Ingestor effect: {len(found)}")

    pctfile = json.loads((HERE / "ingestor_percent.json").read_text())
    labels, pct = pctfile["stat_labels"], pctfile["pct"]

    idx = json.loads((HERE / "nms_index.json").read_text())
    written, unlabelled = 0, set()
    for pid, (stat, dur) in found.items():
        if pid not in idx["items"]:
            continue
        label = labels.get(stat)
        if not label:
            unlabelled.add(stat)
            continue
        entry = {"s": label, "d": dur}
        if pid in pct:
            entry["p"] = pct[pid]
        idx["items"][pid]["ing"] = entry
        written += 1

    have_pct = sum(1 for v in idx["items"].values() if "ing" in v and "p" in v["ing"])
    print(f"written: {written}   with a percentage: {have_pct}")
    if unlabelled:
        print(f"NOTE: {len(unlabelled)} stat(s) have no human label yet, so those items "
              f"were skipped: {sorted(unlabelled)}")
        print("      Add them to stat_labels in ingestor_percent.json.")

    if args.check:
        print("--check: nothing written.")
        return
    (HERE / "nms_index.json").write_text(json.dumps(idx, separators=(",", ":")))
    print("nms_index.json updated.")


if __name__ == "__main__":
    main()
