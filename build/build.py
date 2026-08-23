#!/usr/bin/env python3
"""Build index.html: fetch basemap tiles, inline everything, emit one file.

The published page can't reach a tile server (strict CSP on the host), so the
CARTO basemap is downloaded once, transcoded PNG -> WebP, and embedded as
base64 data URIs. Leaflet is vendored locally for the same reason. The result
is a single self-contained index.html that needs nothing but Google Fonts.

    python3 build/build.py

Requires Pillow.  Place data lives in build/template.html, near the top of the
final <script> block; edit it there and re-run.
"""
import base64, io, json, math, os, pickle, time, urllib.request
from PIL import Image

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL    = os.path.join(ROOT, "build", "template.html")
CACHE  = os.path.join(ROOT, "build", "tiles.pkl")
OUT    = os.path.join(ROOT, "index.html")

# Bounding box: every place, both homes, and all five MRT stations, padded.
LAT0, LAT1 = 1.30620, 1.32400
LNG0, LNG1 = 103.85230, 103.87340
ZOOMS      = (15, 16, 17)          # z18 is upscaled from z17 @2x at runtime
THEMES     = (("L", "light_all"), ("D", "dark_all"))
QUALITY    = 74
UA         = {"User-Agent": "food-recommendation build script"}


def tile_x(lng, z):
    return int((lng + 180.0) / 360.0 * (2 ** z))


def tile_y(lat, z):
    r = math.radians(lat)
    return int((1.0 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2.0 * (2 ** z))


def fetch_tiles():
    if os.path.exists(CACHE):
        print("using cached tiles:", CACHE)
        return pickle.load(open(CACHE, "rb"))
    tiles, subs, i = {}, "abcd", 0
    for theme, slug in THEMES:
        for z in ZOOMS:
            for x in range(tile_x(LNG0, z), tile_x(LNG1, z) + 1):
                for y in range(tile_y(LAT1, z), tile_y(LAT0, z) + 1):
                    url = ("https://%s.basemaps.cartocdn.com/%s/%d/%d/%d@2x.png"
                           % (subs[i % 4], slug, z, x, y))
                    i += 1
                    data = urllib.request.urlopen(
                        urllib.request.Request(url, headers=UA), timeout=30).read()
                    buf = io.BytesIO()
                    Image.open(io.BytesIO(data)).convert("RGB").save(
                        buf, "WEBP", quality=QUALITY, method=6)
                    tiles["%s/%d/%d/%d" % (theme, z, x, y)] = buf.getvalue()
                    time.sleep(0.035)
    pickle.dump(tiles, open(CACHE, "wb"))
    print("fetched %d tiles" % len(tiles))
    return tiles


def main():
    tiles = fetch_tiles()
    encoded = {k: base64.b64encode(v).decode("ascii") for k, v in tiles.items()}
    css = open(os.path.join(ROOT, "vendor", "leaflet.css")).read()
    css = css.replace("url(images/", "url(data:,#")   # default marker icons are unused
    js = open(os.path.join(ROOT, "vendor", "leaflet.js")).read()

    html = open(TPL).read()
    for token in ("/*__LEAFLET_CSS__*/", "/*__LEAFLET_JS__*/", "/*__TILES__*/"):
        assert token in html, "template is missing " + token
    html = (html.replace("/*__LEAFLET_CSS__*/", css)
                .replace("/*__LEAFLET_JS__*/", js)
                .replace("/*__TILES__*/", json.dumps(encoded, separators=(",", ":"))))

    open(OUT, "w").write(html)
    print("wrote %s  (%.2f MB, %d tiles)" % (OUT, os.path.getsize(OUT) / 1e6, len(encoded)))


if __name__ == "__main__":
    main()
