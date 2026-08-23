# Food recommendation

Ten places worth going back to around Boon Keng, Bendemeer and Geylang Bahru — with
what was ordered, what it cost, how it scored, how far it is, and which MRT station
actually serves it.

**Live:** https://fang89.github.io/food-recommendation/

## What it does

- **A real street map** with every place pinned, plus the five MRT stations that come
  out nearest to something on the list — drawn in their real line colours (NE purple,
  DT blue, EW green).
- **Two datums.** Click either home marker, or the switch above the map, and the
  distance rings, measured runs, distances, bearings and walking times all recompute
  from that door.
- **A sortable list.** Sort by place, rating, price, distance from the active door, or
  walk to the nearest MRT. Clicking a row finds that place on the map.
- **A card per place** on click — rating, price band, distance, station, the plus and
  the minus, and a Google Maps walking-directions link that routes from wherever the
  viewer happens to be.

## Updating the list

Anyone can add a row to the sheet. To pull those edits onto the page:

```
./update.sh
git add -A && git commit -m "Refresh from sheet" && git push
```

That is the whole loop. `update.sh` runs two steps:

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

**`build/build.py`** fetches the basemap for the current bounding box, transcodes
it, and inlines Leaflet, the tiles and the data into a single `index.html`. Tiles
are cached per bounding box, so a refresh that does not move the map reuses them.

Read the warnings `refresh.py` prints. They are how the sheet tells you it has
drifted.

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
- Three entries have no plus/minus written up yet and say so.

## Attribution

Basemap © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors,
© [CARTO](https://carto.com/attributions). Geocoding © OneMap, Singapore Land Authority.
