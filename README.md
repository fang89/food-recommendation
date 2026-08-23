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

## How it's built

One self-contained `index.html`. Nothing is fetched at runtime except Google Fonts.

- **Leaflet** is vendored into `vendor/`.
- **The basemap is embedded.** A published page can't reach a tile server, so 212
  CARTO tiles (zoom 15–17, @2x, both light and dark) are downloaded at build time,
  transcoded PNG → WebP, and inlined as base64 data URIs. Zoom 18 is upscaled from
  the z17 @2x tiles. That fixes coverage: the map is bounded to these three estates
  and won't pan past the edge.
- **Both themes ship.** The tile layer swaps with the viewer's light/dark setting.

Rebuild with:

```
python3 build/build.py     # requires Pillow
```

Tiles are cached in `build/tiles.pkl` (gitignored) after the first run.

## The data

Places come from a Google Sheet — name, signature dish tried, plus, minus, rating out
of 5, price band, address. The **Add a place to the sheet** button on the page links
to it.

Coordinates are resolved through [OneMap](https://www.onemap.gov.sg/), Singapore's
national address database. Every address is geocoded twice — once by postal code, once
by street — and the two are compared; where they disagree the postal-code match wins,
since that's what the sheet records. Where a shop sits inside a larger building, the
pin is the building.

Place data lives near the top of the last `<script>` block in `build/template.html`.

## Caveats

- **Distances are geodesic** — straight lines from the datum, not walking routes.
  Allow roughly 15–30% more on foot once crossings and the canal are counted.
- **Distance rings are not isochrones.** They show separation, not reachability.
- Three entries have no plus/minus written up yet and say so.

## Attribution

Basemap © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors,
© [CARTO](https://carto.com/attributions). Geocoding © OneMap, Singapore Land Authority.
