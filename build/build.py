#!/usr/bin/env python3
"""Build index.html: inline Leaflet and the data into one file.

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


def main():
    cfg = load("config.json")

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
    print("wrote %s  (%.2f MB, %d places)"
          % (OUT, os.path.getsize(OUT) / 1e6, len(load("places.json"))))


if __name__ == "__main__":
    main()
