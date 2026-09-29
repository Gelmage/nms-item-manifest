# NMS Item Manifest

Reads a No Man's Sky save and shows what you can actually make with what you
are actually carrying — cooking, refining, crafting, fishing bait — plus a full
map of where every item is stored across every container.

Read-only. Your save is opened, decoded in memory, and never written to.
Nothing is uploaded: the page runs on your own machine.

![Crafting view](screenshots/crafting.png)

## Run it

**Windows** — double-click `NMS Item Manifest (Windows).bat`
**macOS** — double-click `NMS Item Manifest (Mac).command`
**Linux / Steam Deck** — run `./item-manifest.sh`

It finds your save automatically, opens a page in your browser, and reads the
save again whenever you press **Refresh**. Python 3 is required; the wrappers
install the one dependency (`lz4`) for you.

By hand:

    pip install lz4
    python3 manifest.py              open the page
    python3 manifest.py --print      one reading to stdout, no browser
    python3 manifest.py --port 9000  serve somewhere else

## What it shows

**Bait** — all six fishing lures, what you already hold and where, what you can
make now, and what you could make after crafting the missing parts.

**Cooking** — every dish your stock can reach, including ones that need an
intermediate cooked first. Effects and sale values come from the game's own
reward tables. Click any dish for a build plan.

**Refining** — the same reach calculation across the game's 361 refiner recipes.

**Crafting** — the 1,967 items that carry a recipe, solved the same way.

**Inventory** — every container with its real capacity, what it holds, what it
is worth, an item locator that answers "where is my Chromatic Metal", and a
consolidation view showing stacks you could merge and how many slots that frees.

![Inventory view](screenshots/inventory.png)

Capacity is the unlocked-slot count, not the number of occupied slots: the game
only writes slots that hold something, so a chest listing 50 items and a suit
listing 50 items look identical in the file until you read the slot list.

**Cooking**, with effects and values straight from the game's reward tables:

![Cooking view](screenshots/cooking.png)

Build plans spend what you already hold before crafting anything, and list the
operations in the order you would actually do them.

## Where saves are found

Steam on Windows, macOS, Linux and Steam Deck, including Proton prefixes and
games installed on secondary drives (`libraryfolders.vdf` is read). If your save
is somewhere unusual, press **Load a save** on the page and pick `save.hg`
yourself — that path works everywhere and needs no server at all.

The tool reads whichever context the game is actually playing: a save holds both
a normal and an expedition context, and reading the wrong one silently reports
the other save's numbers.

## Building the page

`index.html` is generated. Edit `page.template.html`, then:

    python3 build.py          ship-ready page, contains no save data
    python3 build.py --bake   bakes your current save in, for local use only

**The committed `index.html` contains no save data.** If you run `--bake`, run
`build.py` again before committing.

## Where the game data comes from

Item names, recipes and effects are datamined v7.00 tables from
[bradhave94/nms-data-extractor](https://github.com/bradhave94/nms-data-extractor)
(MIT). The game's own copies live in `HGPAK` archives, which are not PSARC and
would need separate reverse engineering.

**The tables are committed, not downloaded at runtime.** That is deliberate: the
tool then works offline, and cannot be broken by an upstream repository moving
or disappearing. A given commit always behaves the same way.

The cost is that a game patch can make a recipe stale, so refreshing is a
deliberate act:

    python3 refresh_tables.py --check    report what would change
    python3 refresh_tables.py            refresh the tables
    python3 build.py                     rebuild the page

`--check` warns if items have vanished upstream, which is the signal that
something went wrong rather than that the game changed.

Container names come from the MBINCompiler key mapping: the game's stack-size
group is not a name — it reports "Chest" for all ten storage containers.

## Known limits

- Tables are v7.00. A later patch could change a recipe.
- Recipe counts are per-item maximums: each assumes you spend your stock on that
  one item. Read them as a menu, not a sum.
- Procedurally generated items (upgrade modules, artifacts) have no fixed names
  and show as their internal id.
- It answers "can I reach this", not "what is the best use of my stock". It is
  not a scheduler.

## Credits

The LZ4 save reader comes from [nms-core-run](https://github.com/Gelmage/nms-core-run).
