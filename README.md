# Food recommendation

Sixteen places worth going back to around Boon Keng, Bendemeer and Geylang Bahru — with
what was ordered, what it cost, how it scored, how far it is, and which MRT station
actually serves it.

**Live:** https://fang89.github.io/food-recommendation/

## What it does

- **A real street map** with every place pinned, plus the five MRT stations that come
  out nearest to something on the list — drawn in their real line colours (NE purple,
  DT blue, EW green).
- **Three datums.** Click any home marker, or the switch above the map, and the
  distance rings, measured runs, distances, bearings and walking times all recompute
  from that door — and the map recentres on it, since that is what you are now
  measuring from.
- **A sortable list.** Sort by place, rating, price, distance from the active door, or
  walk to the nearest MRT. Clicking a row finds that place on the map.
- **A card per place** on click — rating, price band, distance, station, the plus and
  the minus, and a Google Maps walking-directions link that routes from wherever the
  viewer happens to be.

## Updating the list

Anyone can add a row to the sheet. There are three ways to get those edits onto
the page, in increasing order of permanence.

### 1. From the page itself — **Pull from sheet**

The published page has a **Pull from sheet** button next to the sheet link. It
re-reads the sheet in the browser and redraws the list and the map on the spot:
no terminal, no rebuild, no wait. This works because Google serves the sheet's
CSV export with a CORS header for this site's origin, and OneMap's geocoder
allows any origin — so a row added a minute ago can be located and pinned
client-side.

It tells you what it found (`3 new, 1 updated, 2 removed`) and what it could not
do, and it is explicit that the change is **for that browser tab only**. Nothing
is written back. Reload and you are on the last real build again.

Two things it deliberately cannot do:

- **It never reads the postal-code tab.** Only the food tab's `gid` is compiled
  into the page. The homes are geocoded at build time and only their coordinates
  ship, so a browser pull has no way to reach the postal codes.
- **It cannot re-cut the basemap.** Tiles are baked in over a fixed box. A place
  outside that box still gets its row and its pin, and the page says plainly that
  the map underneath it will be blank until someone rebuilds.

### 2. From GitHub — the **Refresh from sheet** action

Actions → *Refresh from sheet* → **Run workflow**. That does the full job on a
runner — re-geocode, recompute the bounding box, re-cut tiles if the box moved,
smoke test, commit — and Pages redeploys. Still no terminal. It also runs itself
weekly, so the page does not silently rot if nobody presses anything.

### 3. From a terminal

```
./update.sh
git add -A && git commit -m "Refresh from sheet" && git push
```

`update.sh` runs three steps:

**`build/refresh.py`** downloads the sheet, geocodes anything new, and rewrites
`data/places.json`, `data/homes.json` and `data/mrt.json`. It is written to
survive the sheet being edited by hand, because this one already has been:

- the header row moves up and down as blank rows come and go, so it is found by
  looking for `Name of place` rather than by row number
- columns are matched by header text, so reordering or inserting one is fine
- a rating typed into the **Minus** column instead of **Rating** is detected and
  moved, with a warning naming the row
- every address is geocoded twice, once by postal code and once by street name,
  and a disagreement is reported — the postal-code match wins, since that is what
  the sheet records
- the map's bounding box is recomputed from the new points, so a place outside the
  current coverage widens it automatically
- only MRT stations that come out nearest to something are kept, so listing extra
  candidates in `config.json` costs nothing

Geocodes are cached in `build/geocache.json` (committed), so a refresh only calls
OneMap for genuinely new addresses. `--force` re-resolves everything.

**Home lookups are never cached.** The cache file is committed to a public repo,
and it is keyed by the query, so caching a home would publish its postal code —
the one thing this project takes care to keep out. `geocode(..., private=True)`
skips the cache for those, and every write strips any bare postal-code key an
older build may have left behind.

**`build/build.py`** fetches the basemap for the current bounding box, transcodes
it, and inlines Leaflet, the tiles and the data into a single `index.html`. Tiles
are cached per bounding box, so a refresh that does not move the map reuses them.

**`build/smoke.py`** then runs the built page's script against a stubbed Leaflet
and DOM, and fails if the map never got a view, the table body never got written,
or the **Pull from sheet** button cannot complete a round trip against a canned
sheet and geocoder. A syntax check passes happily on code that throws the moment it runs;
this catches the blank-map case, which is otherwise indistinguishable from
"no data yet". It proves the plumbing executes — it says nothing about how the
page looks, so still open it.

Read the warnings `refresh.py` prints. They are how the sheet tells you it has
drifted.

### When a home will not geocode

A home is located from the postal code on the sheet's other tab, and only its
coordinates are written into `data/homes.json` — the postal code itself never
reaches this repo or the page.

If OneMap cannot resolve one, `refresh.py` says so by label and leaves that home
off the map rather than guessing. To place it anyway, add coordinates under
`home_overrides` in `data/config.json`, keyed by the label on the sheet. That
file is public, so an override holds coordinates, not a postal code or a block
number — nothing more identifying than the page already ships. Delete the entry
once the sheet's own code resolves.

## Configuration

`data/config.json` holds everything you would otherwise have to edit code for:
the sheet id and URL, walking speed, display names for the homes, hand-written
short labels for places whose names are too long for the map, the MRT candidate
list, and the tile zoom range and quality.

## How it's built

One self-contained `index.html`. Nothing is fetched at runtime except Google Fonts.

- **Leaflet** is vendored into `vendor/`.
- **The basemap is embedded.** A published page can't reach a tile server, so the
  CARTO tiles (zoom 15-17, @2x, both light and dark) are downloaded at build time,
  transcoded PNG to WebP, and inlined as base64 data URIs. Zoom 18 is upscaled from
  the z17 @2x tiles. That fixes coverage: the map is bounded to these estates and
  won't pan past the edge.
- **Both themes ship.** The tile layer swaps with the viewer's light/dark setting.
- **Place data is never hand-edited.** It comes from `data/*.json`, which comes from
  the sheet.

## Caveats

- **Distances are geodesic** — straight lines from the datum, not walking routes.
  Allow roughly 15–30% more on foot once crossings and the canal are counted.
- **Distance rings are not isochrones.** They show separation, not reachability.
- Entries with no plus/minus written up yet say so.
- **A browser pull is not a build.** It changes what you are looking at, not what
  is published. Use the GitHub action or `./update.sh` to make it stick.

## Attribution

Basemap © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors,
© [CARTO](https://carto.com/attributions). Geocoding © OneMap, Singapore Land Authority.
