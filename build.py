#!/usr/bin/env python3
"""Generate index.html from page.template.html.

By design the shipped page contains NO save data: the placeholder is filled
with an empty reading, so the page opens asking for a save. kitchen.py serves
the real one at runtime.

    python3 build.py            ship-ready page, no save data
    python3 build.py --bake     bake your current save in (local use only —
                                the result must not be committed)
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EMPTY = {"held": {}, "containers": [], "units": None, "nanites": None,
         "quicksilver": None, "context": None, "saveMtime": 0, "savePath": ""}


def build(bake=False):
    payload = EMPTY
    if bake:
        sys.path.insert(0, str(HERE))
        import kitchen
        payload = kitchen.reading()
        print(f"baking {payload['savePath']}: {len(payload['held'])} item types "
              f"- DO NOT COMMIT the result")

    esc = lambda t: t.replace("</", "<\\/")
    html = (HERE / "page.template.html").read_text()
    for token, data in (("__INDEX__", (HERE / "nms_index.json").read_text()),
                        ("__NAMES__", (HERE / "container_names.json").read_text()),
                        ("__BAKED__", json.dumps(payload, separators=(",", ":")))):
        if token not in html:
            raise SystemExit(f"template is missing {token}")
        html = html.replace(token, esc(data))
    out = HERE / "index.html"
    out.write_text(html)
    print(f"wrote {out.name}: {len(html):,} bytes"
          + ("" if bake else "  (no save data)"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bake", action="store_true")
    build(**vars(ap.parse_args()))
