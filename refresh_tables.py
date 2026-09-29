#!/usr/bin/env python3
"""Re-download the game data tables and rebuild nms_index.json.

The tables are baked into the page on purpose: the tool then works offline and
cannot be broken by an upstream repo moving. The cost is that a game patch can
make a recipe stale, so this exists to refresh them deliberately.

    python3 refresh_tables.py           refresh, then run build.py
    python3 refresh_tables.py --check   report what would change, write nothing

Source: https://github.com/bradhave94/nms-data-extractor  (MIT)
"""
import argparse, json, sys, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = ("https://raw.githubusercontent.com/bradhave94/"
        "nms-data-extractor/main/data/json")
# every table that contributes names, recipes, effects or values
FILES = ["Products.json", "RawMaterials.json", "Food.json", "Fish.json",
         "NutrientProcessor.json", "Refinery.json", "Others.json",
         "Creatures.json", "Curiosities.json", "Technology.json", "Trade.json",
         "Upgrades.json", "Exocraft.json", "Starships.json", "Corvette.json",
         "ConstructedTechnology.json", "TechnologyModule.json", "Buildings.json"]


def fetch(name):
    with urllib.request.urlopen(f"{BASE}/{name}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def build_index(tables):
    items, seen_from = {}, {}
    for src, data in tables.items():
        for e in (data if isinstance(data, list) else list(data.values())):
            if not isinstance(e, dict) or not e.get("Id") or not e.get("Name"):
                continue
            if e["Id"] in items:
                continue
            rec = {"n": e["Name"]}
            if e.get("Group"):           rec["g"] = e["Group"]
            if e.get("EffectCategory"):  rec["ec"] = e["EffectCategory"]
            st = e.get("RewardEffectStats")
            if isinstance(st, dict):
                s = {k: v for k, v in st.items() if k != "PercentageChance" and v}
                if s: rec["es"] = s
            if e.get("BaseValueUnits"):  rec["v"] = e["BaseValueUnits"]
            if e.get("CookingValue"):    rec["cv"] = e["CookingValue"]
            ri = e.get("RequiredItems") or []
            if ri: rec["r"] = [[r["Id"], r["Quantity"]] for r in ri if r.get("Id")]
            items[e["Id"]] = rec
            seen_from[e["Id"]] = src

    def recipes(rows):
        out = []
        for r in rows:
            ins, o = r.get("Inputs") or [], r.get("Output") or {}
            if not ins or not o.get("Id"):
                continue
            out.append({"i": [[x["Id"], x.get("Quantity", 1)] for x in ins],
                        "o": o["Id"], "q": o.get("Quantity", 1),
                        "op": r.get("Operation")})
        return out

    fish = [{"id": f["Id"], "n": f["Name"], "q": f.get("Quality"),
             "sz": f.get("FishSize"), "t": f.get("FishingTime"),
             "st": bool(f.get("NeedsStorm")), "v": f.get("BaseValueUnits"),
             "b": f.get("Biomes")} for f in tables["Fish.json"]]

    return {"items": items,
            "cook": recipes(tables["NutrientProcessor.json"]),
            "refine": recipes(tables["Refinery.json"]),
            "fish": fish,
            "src": "bradhave94/nms-data-extractor"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report differences without writing")
    args = ap.parse_args()

    tables = {}
    for name in FILES:
        try:
            tables[name] = fetch(name)
            print(f"  ok   {name}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"  FAIL {name}: {exc}", file=sys.stderr)
            raise SystemExit("aborted - the existing tables were left alone")

    new = build_index(tables)
    out = HERE / "nms_index.json"
    old = json.loads(out.read_text()) if out.exists() else {"items": {}, "cook": [],
                                                            "refine": [], "fish": []}
    print(f"\n  items    {len(old['items']):>6,} -> {len(new['items']):>6,}")
    print(f"  cooking  {len(old['cook']):>6,} -> {len(new['cook']):>6,}")
    print(f"  refining {len(old['refine']):>6,} -> {len(new['refine']):>6,}")
    print(f"  fish     {len(old['fish']):>6,} -> {len(new['fish']):>6,}")

    gone = set(old["items"]) - set(new["items"])
    if gone:
        print(f"  WARNING: {len(gone)} items vanished upstream, e.g. {sorted(gone)[:5]}")

    if args.check:
        print("\n  --check: nothing written")
        return
    out.write_text(json.dumps(new, separators=(",", ":")))
    print(f"\n  wrote {out.name} ({out.stat().st_size/1024:.0f} KB)")
    print("  now run:  python3 build.py")


if __name__ == "__main__":
    main()
