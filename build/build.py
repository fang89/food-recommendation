#!/usr/bin/env python3
"""Build index.html: fetch basemap tiles, inline everything, emit one file.

The published page can't reach a tile server (strict CSP on the host), so the
CARTO basemap is downloaded once, transcoded PNG -> WebP, and embedded as
base64 data URIs. Leaflet is vendored locally for the same reason. The result
is a single self-contained index.html that needs nothing but Google Fonts.

    python3 build/refresh.py    # pull the sheet, geocode, write data/*.json
    python3 build/build.py      # inline everything, emit index.html

or just ./update.sh, which runs both.  Requires Pillow.  Place data comes from
data/*.json and is never edited by hand.
"""
import base64, hashlib, io, json, math, os, pickle, time, urllib.request
from PIL import Image

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL    = os.path.join(ROOT, "build", "template.html")
DATA   = os.path.join(ROOT, "data")
OUT    = os.path.join(ROOT, "index.html")

THEMES = (("L", "light_all"), ("D", "dark_all"))   # z18 is upscaled from z17 @2x
UA     = {"User-Agent": "food-recommendation build script"}


def load(name):
    return json.load(open(os.path.join(DATA, name)))


def cache_path(bbox, zooms):
    """Tiles are cached per bounding box, so moving the bbox refetches by itself."""
    key = hashlib.sha1(json.dumps([bbox, zooms], sort_keys=True).encode()).hexdigest()[:10]
    return os.path.join(ROOT, "build", "tiles-%s.pkl" % key)


def tile_x(lng, z):
    return int((lng + 180.0) / 360.0 * (2 ** z))


def tile_y(lat, z):
    r = math.radians(lat)
    return int((1.0 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2.0 * (2 ** z))


def fetch_tiles(bbox, zooms, quality):
    cache = cache_path(bbox, zooms)
    if os.path.exists(cache):
        print("using cached tiles:", os.path.basename(cache))
        return pickle.load(open(cache, "rb"))
    tiles, subs, i = {}, "abcd", 0
    for theme, slug in THEMES:
        for z in zooms:
            for x in range(tile_x(bbox["lng0"], z), tile_x(bbox["lng1"], z) + 1):
                for y in range(tile_y(bbox["lat1"], z), tile_y(bbox["lat0"], z) + 1):
                    url = ("https://%s.basemaps.cartocdn.com/%s/%d/%d/%d@2x.png"
                           % (subs[i % 4], slug, z, x, y))
                    i += 1
                    data = urllib.request.urlopen(
                        urllib.request.Request(url, headers=UA), timeout=30).read()
                    buf = io.BytesIO()
                    Image.open(io.BytesIO(data)).convert("RGB").save(
                        buf, "WEBP", quality=quality, method=6)
                    tiles["%s/%d/%d/%d" % (theme, z, x, y)] = buf.getvalue()
                    time.sleep(0.035)
    pickle.dump(tiles, open(cache, "wb"))
    print("fetched %d tiles" % len(tiles))
    return tiles


def main():
    cfg = load("config.json")
    zooms = tuple(cfg.get("zooms", [15, 16, 17]))
    tiles = fetch_tiles(cfg["bbox"], zooms, cfg.get("tile_quality", 74))
    encoded = {k: base64.b64encode(v).decode("ascii") for k, v in tiles.items()}
    css = open(os.path.join(ROOT, "vendor", "leaflet.css")).read()
    css = css.replace("url(images/", "url(data:,#")   # default marker icons are unused
    js = open(os.path.join(ROOT, "vendor", "leaflet.js")).read()

    # Only what the page needs at runtime. The sheet id and the FOOD tab's gid
    # go in so the published page can re-read the sheet itself; the postal-code
    # tab is never named here, so a browser pull can never reach it.
    runtime = {"bbox": cfg["bbox"], "walk": cfg.get("walk_speed_m_per_min", 80),
               "sheet_id": cfg["sheet_id"], "sheet_gid": cfg["sheet_gid"],
               "short_names": cfg.get("short_names", {})}
    subs = {
        "/*__LEAFLET_CSS__*/": css,
        "/*__LEAFLET_JS__*/":  js,
        "/*__TILES__*/":       json.dumps(encoded, separators=(",", ":")),
        "/*__CONFIG__*/":      json.dumps(runtime, separators=(",", ":")),
        "/*__HOMES__*/":       json.dumps(load("homes.json"),  separators=(",", ":")),
        "/*__MRT__*/":         json.dumps(load("mrt.json"),    separators=(",", ":")),
        "/*__PLACES__*/":      json.dumps(load("places.json"), separators=(",", ":")),
        "__SHEET_URL__":       cfg["sheet_url"],
    }
    html = open(TPL).read()
    for token, value in subs.items():
        assert token in html, "template is missing " + token
        html = html.replace(token, value)

    open(OUT, "w").write(html)
    print("wrote %s  (%.2f MB, %d places, %d tiles)"
          % (OUT, os.path.getsize(OUT) / 1e6, len(load("places.json")), len(encoded)))


if __name__ == "__main__":
    main()
