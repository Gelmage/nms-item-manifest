#!/usr/bin/env python3
"""Nutrient Processor - No Man's Sky cooking, crafting and inventory.

Serves the page and re-reads the save on demand, so the Refresh button in the
browser shows what is in your ship right now. Read-only: the save is opened,
decoded in memory, never written.

    python3 manifest.py                 open the page
    python3 manifest.py --port 8788     serve somewhere else
    python3 manifest.py --print         dump a reading to stdout and exit
    python3 manifest.py --no-browser    serve only, open the URL yourself

Windows, macOS, Linux and Steam Deck. The save is found automatically; nothing
is uploaded and nothing is ever written back to it.
"""
import argparse, json, os, platform, shutil, subprocess, sys, threading
import urllib.error, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# When PyInstaller freezes this into an exe, the bundled data files are
# unpacked to a temporary directory that sys._MEIPASS points at; __file__ then
# points somewhere useless. Everything read at runtime must resolve from HERE.
FROZEN = getattr(sys, "frozen", False)
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE))
import nms_save

PAGE = HERE / "index.html"
# key -> human label, resolved from the MBINCompiler mapping. The stack-size
# group is NOT a name: it reports "Chest" for all ten storage containers.
try:
    NAMES = json.loads((HERE / "container_names.json").read_text())
except OSError:
    NAMES = {}
DEFAULT_PORT = 8788          # core-run owns 8787

# Keys resolved from MBINCompiler mapping 6.11.0.1. Verified 2026-09-25.
ACTIVE_CONTEXT = "XTp"
CONTEXTS = {"Main": "vLc", "Season": "2YS"}
PLAYER_STATE = "6f="
SLOTS, VALID_SLOTS, ITEM_ID, AMOUNT = ":No", "hl?", "b2n", "1o9"
STACK_GROUP, CLASS, NAME = "WA4", "B@N", "NKm"
# Ships carry Inventory / Cargo / TechOnly directly, not a Store like a chest.
SHIP_INV = (";l5", "gan", "PMT")
SHIPS, TOOLS, ARCHIVED, VEHICLES = "@Cs", "SuJ", "R@v", "P;m"
STORE, TOOL_DATA = "OsQ", "97S"
UNITS, NANITES, SPECIALS = "wGS", "7QL", "kN;"


def player_state(root):
    """The PlayerStateData the game is actually playing.

    Reading the wrong context silently reports the other save's numbers - the
    expedition context held 75,207 units against the base context's 597 million.
    """
    key = CONTEXTS.get(root.get(ACTIVE_CONTEXT))
    ps = (root.get(key) or {}).get(PLAYER_STATE) if key else None
    if isinstance(ps, dict):
        return ps
    best, size = None, -1
    for ctx in CONTEXTS.values():
        cand = (root.get(ctx) or {}).get(PLAYER_STATE)
        if not isinstance(cand, dict):
            continue
        n = sum(len(v[SLOTS]) for v in cand.values()
                if isinstance(v, dict) and isinstance(v.get(SLOTS), list))
        if n > size:
            best, size = cand, n
    if best is None:
        raise RuntimeError("No PlayerStateData found - is this a save.hg?")
    return best


MAX_AMOUNT, SLOT_TYPE, TYPE_NAME = "F9q", "Vn8", "elv"


def read_slots(slots):
    """(id, amount, max-per-stack, kind) for each occupied slot.

    max and kind are what make consolidation answerable: a damaged ship slot and
    a stack of Carbon both look like items until you read the type.
    """
    out = []
    for s in slots or []:
        if not isinstance(s, dict):
            continue
        iid, qty = s.get(ITEM_ID), s.get(AMOUNT)
        if not isinstance(iid, str) or not iid.startswith("^"):
            continue
        if not isinstance(qty, int) or qty <= 0:
            continue
        out.append((iid.lstrip("^").split("#")[0], qty,
                    s.get(MAX_AMOUNT) or 0,
                    (s.get(SLOT_TYPE) or {}).get(TYPE_NAME) or ""))
    return out


def containers(ps):
    """Every store, with where it is and how much room is left.

    Capacity is ValidSlotIndices, not len(Slots): the game only writes occupied
    slots, so a Slots array of 50 in a 50-slot chest and in a 120-slot suit look
    identical until you read the unlocked-slot list.
    """
    found = []

    def add(label, node, kind):
        if not isinstance(node, dict):
            return
        slots = node.get(SLOTS)
        if not isinstance(slots, list):
            return
        # a container the player renamed in game beats anything we map
        own = node.get(NAME)
        if isinstance(own, str) and own.strip():
            label = own.strip()
        valid = node.get(VALID_SLOTS)
        cap = len(valid) if isinstance(valid, list) else len(slots)
        found.append({
            "label": label,
            "kind": kind,
            "cls": (node.get(CLASS) or {}).get("1o6"),
            "used": len(slots),
            "cap": cap,
            "items": [{"id": i, "n": q, "m": m, "t": t}
                      for i, q, m, t in read_slots(slots)],
        })

    for key, v in ps.items():
        if isinstance(v, dict) and isinstance(v.get(SLOTS), list):
            group = (v.get(STACK_GROUP) or {}).get("rri") or "Storage"
            add(NAMES.get(key, group), v, group)
    for i, sh in enumerate(ps.get(SHIPS) or [], 1):
        base = (sh.get(NAME) or "").strip() or f"Starship {i}"
        for key, suffix in zip(SHIP_INV, ("", " \u2014 Cargo", " \u2014 Technology")):
            add(base + suffix, sh.get(key), "Starship")
    for i, v in enumerate(ps.get(VEHICLES) or [], 1):
        base = (v.get(NAME) or "").strip() or f"Exocraft {i}"
        for key, suffix in zip(SHIP_INV, ("", " \u2014 Cargo", " \u2014 Technology")):
            add(base + suffix, v.get(key), "Exocraft")
    for i, t in enumerate(ps.get(TOOLS) or [], 1):
        add(t.get("NKm") or f"Multitool {i}",
            (t.get(TOOL_DATA) or {}).get(STORE) or t.get(STORE), "Multitool")
    for i, t in enumerate(ps.get(ARCHIVED) or [], 1):
        add(t.get("NKm") or f"Stored multitool {i}",
            (t.get(TOOL_DATA) or {}).get(STORE) or t.get(STORE), "Multitool")
    return [c for c in found if c["cap"] or c["items"]]


def reading(save_path=None):
    save = Path(nms_save.newest_save(save_path))
    root = nms_save.decompress(save)
    ps = player_state(root)
    cons = containers(ps)

    held = {}
    for c in cons:
        for it in c["items"]:
            held[it["id"]] = held.get(it["id"], 0) + it["n"]

    return {
        "held": held,
        "containers": cons,
        "units": ps.get(UNITS), "nanites": ps.get(NANITES),
        "quicksilver": ps.get(SPECIALS),
        "context": root.get(ACTIVE_CONTEXT),
        "saveMtime": int(save.stat().st_mtime),
        "savePath": save.name,
    }


class Reader:
    """Re-reads only when the file has actually changed. A stat() is cheap;
    inflating eleven megabytes of JSON is not."""

    def __init__(self):
        self._stamp = None
        self._data = None

    def current(self, force=False):
        try:
            newest = Path(nms_save.newest_save())
            stamp = (str(newest), newest.stat().st_mtime_ns)
            if force or stamp != self._stamp or self._data is None:
                self._data = reading()
                self._stamp = stamp
            return self._data, None
        except Exception as exc:
            return self._data, f"{type(exc).__name__}: {exc}"


class Handler(BaseHTTPRequestHandler):
    reader = None

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"index.html is missing.", "text/plain; charset=utf-8")
            return
        if path == "/data.json":
            data, error = self.reader.current(force="force=1" in self.path)
            self._send(200, json.dumps({"ok": error is None, "error": error,
                                        "data": data}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")


def _app_mode_browser():
    """A Chromium-family browser that supports --app=, or None.

    An app window has no address bar or tabs, which suits a tool. Falling back
    to an ordinary tab is fine, so nothing here is fatal.
    """
    names = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
             "brave-browser", "microsoft-edge", "vivaldi"]
    system = platform.system()
    if system == "Windows":
        for exe in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
            if Path(exe).exists():
                return exe
        return None
    if system == "Darwin":
        for app in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"):
            if Path(app).exists():
                return app
        return None
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    return None


def open_window(url):
    """Open the page, as an app window when one is available."""
    browser = _app_mode_browser()
    if browser:
        try:
            subprocess.Popen([browser, f"--app={url}", "--window-size=1200,900"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=(os.name != "nt"))
            return
        except OSError:
            pass
    webbrowser.open(url)


def already_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/data.json", timeout=1.5) as r:
            json.loads(r.read().decode("utf-8"))
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--print", action="store_true", dest="dump")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if args.dump:
        d = reading()
        print(f"{d['savePath']} [{d['context']}]  {len(d['held'])} item types, "
              f"{d['units']:,} units, {len(d['containers'])} containers")
        return

    url = f"http://127.0.0.1:{args.port}/"
    if already_running(args.port):
        print(f"already serving on {url}")
    else:
        try:
            save = nms_save.newest_save()
            print(f"reading {Path(save).name}")
        except Exception as exc:
            print(f"warning: no save found yet ({exc})", file=sys.stderr)
            print("the page will still open; use 'Load a save' to pick one by hand",
                  file=sys.stderr)
        Handler.reader = Reader()
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
        threading.Thread(target=server.serve_forever, daemon=False).start()
        print(f"serving on {url}   (Ctrl+C to stop)")
    if not args.no_browser:
        open_window(url)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        msg = f"NMS Item Manifest could not start:\n\n{exc}"
        print(msg, file=sys.stderr)
        # a desktop launcher has no console, so try for a dialog too
        for cmd in (["kdialog", "--error", msg],
                    ["zenity", "--error", "--text", msg],
                    ["osascript", "-e", f'display alert "NMS Item Manifest" message "{exc}"']):
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                break
            except Exception:
                continue
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, str(exc), "NMS Item Manifest", 0x10)
            except Exception:
                pass
        # a double-clicked window closes instantly without this; a CI runner
        # would hang on it forever, so skip when automation is detected
        interactive = (sys.stdin and sys.stdin.isatty()
                       and not os.environ.get("CI")
                       and not os.environ.get("GITHUB_ACTIONS"))
        if interactive:
            try:
                input("\nPress Enter to close.")
            except EOFError:
                pass
        raise
