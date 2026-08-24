#!/usr/bin/env python3
"""Re-pull the food list from the Google Sheet and rewrite data/*.json.

    python3 build/refresh.py          # pull, geocode, write data files
    python3 build/refresh.py --force  # ignore the geocode cache

Run this whenever anyone edits the sheet, then run build/build.py to rebuild
index.html.  ./update.sh does both.

The sheet must be shared as "anyone with the link can view" — the export
endpoint returns HTTP 401 otherwise, and this script will say so.

What it copes with, because the sheet has done all of it already:
  * the header row moving up and down as blank rows are added and removed
  * columns being reordered (everything is matched by header text, not position)
  * a rating typed into the Minus column instead of the Rating column
  * a place whose postal code and street name geocode to different points
"""
import argparse
import csv
import datetime
import hashlib
import html as html_mod, io, json, math, os, re, sys, time
import urllib.error, urllib.parse, urllib.request, zipfile

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA     = os.path.join(ROOT, "data")
CONFIG   = os.path.join(DATA, "config.json")
GEOCACHE = os.path.join(ROOT, "build", "geocache.json")
ONEMAP   = "https://www.onemap.gov.sg/api/common/elastic/search"


def write_json(path, obj, **kw):
    """json.dump, plus the trailing newline it does not write.

    Without it every one of these files ends mid-line, so each refresh shows a
    churned last line in the diff whether or not anything in it changed.
    """
    with open(path, "w") as fh:
        json.dump(obj, fh, **kw)
        fh.write("\n")

# Header text -> field name.  Matching is case-insensitive on the prefix, so
# "Rating (5 pt system)" and a later "Rating /5" both land on `rating`.
COLUMNS = [("name of place", "name"), ("category", "cat"), ("signature dish", "cat"),
           ("recommended by", "by"), ("plus", "plus"),
           ("minus", "minus"), ("rating", "rating"), ("price", "price"),
           ("link / address", "addr"), ("address", "addr")]


# ---------------------------------------------------------------- sheet ----

def download_workbook(sheet_id):
    url = "https://docs.google.com/spreadsheets/d/%s/export?format=xlsx" % sheet_id
    req = urllib.request.Request(url, headers={"User-Agent": "food-recommendation refresh"})
    try:
        return urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("The sheet is private (HTTP 401).\n"
                     "Open it, then Share -> General access -> Anyone with the link -> Viewer.")
        raise


def read_sheets(blob):
    """Return [[{col_letter: value}, ...rows], ...tabs] for every tab."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        xml = z.read("xl/sharedStrings.xml").decode()
        shared = [re.sub(r"<[^>]+>", "", m)
                  for m in re.findall(r"<si>(.*?)</si>", xml, re.S)]
    tabs = []
    for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
        rows, xml = [], z.read(name).decode()
        for raw in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
            cells = {}
            # An empty-but-styled cell is written self-closing - <c r="E5" s="1"/>
            # - with no </c> of its own. Matching only <c ...>...</c> made such a
            # cell swallow the NEXT cell's value and file it under its own letter,
            # so a blank Minus quietly stole the Rating beside it. Match both forms.
            for ref, _row, attrs, inner in re.findall(
                    r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', raw, re.S):
                if not inner:
                    continue
                inline = re.search(r"<is>(.*?)</is>", inner, re.S)
                value  = re.search(r"<v>(.*?)</v>", inner, re.S)
                if inline:
                    val = re.sub(r"<[^>]+>", "", inline.group(1))
                elif value:
                    val = value.group(1)
                    if 't="s"' in attrs:
                        val = shared[int(val)]
                else:
                    continue
                val = html_mod.unescape(val).strip()
                if val:
                    cells[ref] = val
            if cells:
                rows.append(cells)
        tabs.append(rows)
    return tabs


def find_header(rows):
    """Locate the header row wherever it has drifted to, and map letter -> field."""
    for i, cells in enumerate(rows):
        if any(v.strip().lower() == "name of place" for v in cells.values()):
            mapping = {}
            for letter, text in cells.items():
                low = text.strip().lower()
                for prefix, field in COLUMNS:
                    if low.startswith(prefix):
                        mapping.setdefault(letter, field)
                        break
            return i, mapping
    sys.exit('No header row found: expected a cell reading "Name of place".')


def parse_places(rows, warnings):
    start, cols = find_header(rows)
    out = []
    for cells in rows[start + 1:]:
        rec = {}
        for letter, field in cols.items():
            if letter in cells:
                rec[field] = cells[letter]
        if not rec.get("name") or not rec.get("addr"):
            continue

        # There was a rescue here that moved a bare 0-5 number out of Minus or
        # Plus into Rating, on the theory that people mistype columns. Nobody
        # had. Every case it "rescued" was this file's own xlsx reader stealing
        # the Rating cell whenever the Minus beside it was empty - see
        # read_sheets. The rescue made a parser bug look like a sheet habit and
        # kept it alive for weeks, so it is gone: a rating in the wrong column
        # now shows up as unrated and says so.
        try:
            rec["rating"] = round(float(rec.get("rating", 0)), 1)
        except ValueError:
            warnings.append("%s: rating %r is not a number - treated as unrated."
                            % (rec["name"], rec.get("rating")))
            rec["rating"] = 0.0

        band = re.sub(r"[^$]", "", rec.get("price", "")) or "$"
        rec["price"] = band[:3]
        rec["plus"]  = rec.get("plus", "")
        rec["minus"] = rec.get("minus", "")
        rec["cat"]   = rec.get("cat", "")
        rec["by"]    = rec.get("by", "")
        out.append(rec)
    return out


def homes_tab(tabs, food, warnings):
    """Which tab holds the postal codes - asked, not assumed.

    This used to be "whichever tab is not the food list", so tab order was
    load-bearing and invisible: drag a tab left in Google Sheets, or add a
    third, and homes come from the wrong rows. The tab says which it is.
    """
    others = [t for t in tabs if t is not food]
    named = [t for t in others
             if any(re.search(r"postal\s*code", v, re.I)
                    for cells in t for v in cells.values())]
    if named:
        return named[0]
    if others:
        warnings.append('No tab has a heading saying "postal code", so the homes '
                        "were read from whichever tab is not the food list. Add "
                        "that heading to say which tab it is.")
        return others[0]
    return []


def postal_column(rows):
    """The column that holds six-digit numbers, not any cell that looks like one.

    A price, a year or a phone number anywhere on the tab was otherwise enough
    to be geocoded and drawn as somebody's front door.
    """
    tally = {}
    for cells in rows:
        for letter, value in cells.items():
            if re.fullmatch(r"\d{6}(\.0)?", value):
                tally[letter] = tally.get(letter, 0) + 1
    return max(tally, key=lambda c: (tally[c], c)) if tally else None


def parse_homes(rows, labels, warnings):
    """Homes are named by config, in tab order - never by what the sheet calls them.

    The sheet labels these rows with the names of the people who live behind
    them, which is how the people editing it think of them, and it is the one
    thing on that tab besides the postal codes worth keeping off a public page.
    So the sheet is read only far enough to know a row is a home; the name the
    page shows comes from config.home_labels, and the sheet's own text is never
    published - not into homes.json, not into a warning, and so not into a
    public Actions log either.

    Which label lands on which home is therefore tab order, and reordering the
    rows swaps them. That costs nothing here that it would cost with real
    names: the labels carry no meaning to a stranger, and the only person who
    can tell a swap has happened is the one who can also see it on the map.
    """
    col = postal_column(rows)
    if col is None:
        return []
    out = []
    for cells in rows:
        raw = cells.get(col, "")
        if not re.fullmatch(r"\d{6}(\.0)?", raw):
            continue
        postal = raw.split(".")[0]
        if len(out) < len(labels):
            label = labels[len(out)]
        else:
            label = "Home %d" % (len(out) + 1)
            warnings.append("Home row %d has no name in config.home_labels - "
                            'calling it "%s". Add one to name it.'
                            % (len(out) + 1, label))
        out.append({"name": label, "postal": postal})
    return out


# ------------------------------------------------------------- geocoding ----

def onemap(query, tries=4):
    url = ONEMAP + "?searchVal=" + urllib.parse.quote(query) + \
          "&returnGeom=Y&getAddrDetails=Y&pageNum=1"
    for attempt in range(tries):
        try:
            return json.load(urllib.request.urlopen(url, timeout=25))
        except Exception:
            time.sleep(3 * (attempt + 1))
    return {"found": 0, "results": []}


def geocode(address, cache, warnings, force=False, private=False):
    """Resolve twice - by postal code and by street - and compare the two.

    private=True keeps the query and its match out of the shared cache.
    build/geocache.json is committed to a public repo, so a home postal code
    written there would publish the very thing the page takes care to hide.
    """
    if not force and not private and address in cache:
        return cache[address]

    postal = re.search(r"\b(\d{6})\b", address)
    street = re.sub(r"#\S+|,.*$", "", address).strip()

    best = None
    if postal:
        res = onemap(postal.group(1)).get("results")
        if res:
            best = res[0]
        time.sleep(2.2)
    alt = None
    if street:
        res = onemap(street).get("results")
        if res:
            alt = res[0]
        time.sleep(2.2)

    chosen = best or alt
    if not chosen:
        if not private:
            warnings.append("%s: OneMap found nothing - not plotted." % address)
        return None
    if best and alt:
        far = abs(float(best["LATITUDE"]) - float(alt["LATITUDE"])) > 1e-5 or \
              abs(float(best["LONGITUDE"]) - float(alt["LONGITUDE"])) > 1e-5
        if far:
            warnings.append("%s: postal code and street name geocode to different "
                            "points - used the postal-code match (%s)."
                            % (address, best["ADDRESS"]))

    entry = {"lat": float(chosen["LATITUDE"]), "lng": float(chosen["LONGITUDE"]),
             "matched": chosen["ADDRESS"]}
    if not private:
        cache[address] = entry
    return entry


# ----------------------------------------------------------------- maths ----

def shorten(name, limit=24):
    """Map labels have to fit: drop any " @ venue" tail, then cut on a word."""
    stem = re.split(r"\s+@\s+", name)[0].strip()
    if len(stem) <= limit:
        return stem
    cut = stem[:limit].rsplit(" ", 1)[0].rstrip(",;-")
    return (cut or stem[:limit]) + "\u2026"


def assign_ids(places, warnings):
    """Give every place an id no other place has.

    An id keys a marker and a table row, so a collision drops one place off the
    map with nothing said. Nine of these names already reach the 28-character
    cut, and the sheet carries two stalls in one food centre, so two outlets of
    one long-named chain is all it takes.
    """
    taken = set()
    for rec in places:
        slug = re.sub(r"[^a-z0-9]+", "-", rec["name"].lower()).strip("-")
        ident = slug[:28].rstrip("-") or "place"
        if ident in taken:
            tag = hashlib.sha1(rec["name"].encode("utf-8")).hexdigest()[:4]
            ident = ident[:23].rstrip("-") + "-" + tag
            warnings.append("%s: its name shortens to an id another place already "
                            "has, so it is now %r." % (rec["name"], ident))
        taken.add(ident)
        rec["id"] = ident
    return places


def haversine(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = p2 - p1
    dl = math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))



def csv_crosscheck(cfg, places, warnings):
    """Compare what we read from the .xlsx with what the page's own pull reads.

    Note that these are two separate downloads of the same sheet. A sheet being
    edited while the build runs can therefore report a disagreement that is
    really just a few seconds of drift - if a warning here names one field of
    one row, rebuild before going looking for a bug.

    The published page re-reads this sheet in the browser, over
    /export?format=csv, with a second parser. If the two disagree about a name
    or an address, every pull will report places as new-and-removed forever and
    re-geocode them. Cheap to check here; invisible otherwise.
    """
    url = ("https://docs.google.com/spreadsheets/d/%s/export?format=csv&gid=%s"
           % (cfg["sheet_id"], cfg["sheet_gid"]))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "food-recommendation refresh"})
        text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
        rows = list(csv.reader(io.StringIO(text)))
    except Exception as exc:
        warnings.append("Could not cross-check against the CSV export (%s). "
                        "The page's own pull may disagree with this build." % exc)
        return

    head = next((i for i, r in enumerate(rows)
                 if any(c.strip().lower() == "name of place" for c in r)), None)
    if head is None:
        warnings.append('The CSV export has no "Name of place" row, so the '
                        "page's Pull from sheet button cannot work.")
        return

    col = {}
    for idx, cell in enumerate(rows[head]):
        low = cell.strip().lower()
        for prefix, field in COLUMNS:
            if low.startswith(prefix):
                col.setdefault(field, idx)
                break
    if "name" not in col or "addr" not in col:
        warnings.append("The CSV export is missing a name or address column, so "
                        "the page's Pull from sheet button cannot work.")
        return

    seen, csv_fields = set(), {}
    for row in rows[head + 1:]:
        get = lambda f: (row[col[f]].strip() if col.get(f, -1) < len(row) else "")
        if get("name") and get("addr"):
            seen.add((get("name"), get("addr")))
            csv_fields[get("name")] = {f: get(f) for f in ("cat", "by", "plus",
                                                           "minus", "rating", "price")}

    # Compare the CONTENT of every column too, not just which rows exist. This
    # check used to stop at (name, address), which is why an xlsx reader that
    # shifted a whole row's values one column left went unseen: the names and
    # addresses still lined up perfectly.
    for rec in places:
        theirs = csv_fields.get(rec["name"])
        if not theirs:
            continue
        for field in ("cat", "by", "plus", "minus", "price"):
            mine = str(rec.get(field, "")).strip()
            if mine != theirs[field]:
                warnings.append("%s: the two parsers disagree about %s - this build "
                                "reads %r, the CSV reads %r." % (rec["name"], field,
                                                                 mine, theirs[field]))
        try:
            same = abs(float(rec.get("rating") or 0) - float(theirs["rating"] or 0)) < 1e-9
        except ValueError:
            same = False
        if not same:
            warnings.append("%s: the two parsers disagree about rating - this build "
                            "reads %r, the CSV reads %r."
                            % (rec["name"], rec.get("rating"), theirs["rating"]))

    ours = {(p["name"], p["addr"]) for p in places}
    only_here = ours - seen
    only_csv  = seen - ours
    for name, addr in sorted(only_here):
        warnings.append("%s: this build reads the address as %r, the CSV the page "
                        "pulls does not - the page will treat it as a new place "
                        "on every pull." % (name, addr))
    for name, addr in sorted(only_csv):
        if name not in {n for n, _ in ours}:
            warnings.append("%s (%s): in the CSV but not in this build." % (name, addr))


# ---------------------------------------------------------------- routing ----

ROUTES  = os.path.join(DATA, "routes.json")
AUTH    = os.path.join(ROOT, "build", "onemap.auth.json")
ROUTE   = "https://www.onemap.gov.sg/api/public/routingsvc/route"
TOKENURL = "https://www.onemap.gov.sg/api/auth/post/getToken"


def onemap_token(warnings):
    """A OneMap routing token, or None if nobody has supplied a login.

    Routing is the one OneMap service that is not open: search answers anybody,
    routing wants a bearer token. The login is read from the environment first
    so CI can pass it as a secret, then from build/onemap.auth.json, which is
    gitignored - this repo is public and a password in it would be a password
    published.
    """
    creds = json.load(open(AUTH)) if os.path.exists(AUTH) else {}

    # A token straight from the OneMap dashboard is enough, and is the only
    # thing needed for a one-off local build. It expires in about three days,
    # so CI wants the email and password instead and mints its own.
    token = os.environ.get("ONEMAP_TOKEN") or creds.get("token")
    if token:
        return token

    email = os.environ.get("ONEMAP_EMAIL") or creds.get("email")
    password = os.environ.get("ONEMAP_PASSWORD") or creds.get("password")
    if not (email and password):
        warnings.append("No OneMap login, so travel times could not be looked up. "
                        "The page falls back to straight-line distance. Put the "
                        "login in ONEMAP_EMAIL / ONEMAP_PASSWORD or in "
                        "build/onemap.auth.json.")
        return None
    try:
        body = json.dumps({"email": email, "password": password}).encode()
        req = urllib.request.Request(TOKENURL, data=body,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "food-recommendation refresh"})
        return json.load(urllib.request.urlopen(req, timeout=30))["access_token"]
    except Exception as exc:
        warnings.append("OneMap would not issue a routing token (%s). Travel times "
                        "fall back to straight-line distance." % exc)
        return None


def route_when(text):
    """Turn "Mon 12:30" into the next such moment, as OneMap wants it.

    OneMap's routing service wants MM-DD-YYYY, and rejects anything else with
    a 400 that names the format - which is the one kind of API error worth
    having.
    """
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    want, clock = (text.split() + ["12:30"])[:2]
    today = datetime.date.today()
    ahead = (days.index(want) - today.weekday()) % 7 or 7
    day = today + datetime.timedelta(days=ahead)
    return day.strftime("%m-%d-%Y"), clock if clock.count(":") == 2 else clock + ":00"


def ask_route(token, mode, a, b, when):
    """One leg, one mode. Returns minutes and walking metres, or None."""
    args = {"start": "%.6f,%.6f" % (a["lat"], a["lng"]),
            "end":   "%.6f,%.6f" % (b["lat"], b["lng"]),
            "routeType": mode}
    if mode == "pt":
        args.update({"date": when[0], "time": when[1], "mode": "TRANSIT",
                     "maxWalkDistance": "1200", "numItineraries": "1"})
    url = ROUTE + "?" + urllib.parse.urlencode(args)
    req = urllib.request.Request(url, headers={"Authorization": token,
                                               "User-Agent": "food-recommendation refresh"})
    for attempt in range(4):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=30))
            break
        except Exception:
            time.sleep(1.2 * (attempt + 1))
    else:
        return None

    if mode == "walk":
        summary = (data.get("route_summary") or {})
        if "total_time" not in summary:
            return None
        return {"min": max(1, round(summary["total_time"] / 60)),
                "walk_m": round(summary.get("total_distance", 0))}

    plan = (data.get("plan") or {}).get("itineraries") or []
    if not plan:
        return None
    best = plan[0]
    legs = [l for l in best.get("legs", []) if l.get("mode") != "WALK"]
    if not legs:
        return None                      # "public transport" that is all walking

    # Say train or bus, not "public transport". OneMap answers with whatever is
    # quickest, and for a couple of these places that is a bus - calling that a
    # train would send somebody to the wrong end of the street.
    kinds = {"train" if l.get("mode") in ("SUBWAY", "RAIL", "TRAM") else "bus"
             for l in legs}
    return {"min": max(1, round(best["duration"] / 60)),
            "walk_m": round(best.get("walkDistance", 0)),
            "changes": int(best.get("transfers") or max(0, len(legs) - 1)),
            "by": " + ".join(sorted(kinds)),
            "via": " \u2192 ".join(l.get("route") or l.get("mode", "") for l in legs)[:40]}


def travel_times(cfg, homes, places, warnings):
    """Fill data/routes.json with a walk and a train+walk time for every pair.

    Keyed by rounded coordinates, not by name or id, so renaming a place on the
    sheet costs nothing and moving one asks again - which is the behaviour you
    want from a cache of "how long does it take to get from here to there".
    """
    cache = json.load(open(ROUTES)) if os.path.exists(ROUTES) else {}
    pairs = [(h, p) for h in homes for p in places]
    key = lambda a, b: "%.5f,%.5f>%.5f,%.5f" % (a["lat"], a["lng"], b["lat"], b["lng"])
    missing = [(h, p) for h, p in pairs if key(h, p) not in cache]
    if not missing:
        return cache

    token = onemap_token(warnings)
    if not token:
        return cache

    when = route_when(cfg.get("route_when", "Mon 12:30"))
    print("  routing %d new pairs (%s %s)" % (len(missing), when[0], when[1]))
    got = 0
    for home, place in missing:
        walk = ask_route(token, "walk", home, place, when)
        transit = ask_route(token, "pt", home, place, when)
        if not walk and not transit:
            warnings.append("No route from %s to %s - that pair keeps its "
                            "straight-line distance." % (home["name"], place["name"]))
            continue
        cache[key(home, place)] = {k: v for k, v in
                                   (("walk", walk), ("pt", transit)) if v}
        got += 1
        time.sleep(0.25)                      # OneMap rate-limits a burst
    write_json(ROUTES, cache, indent=1, sort_keys=True, ensure_ascii=False)
    print("  %d pairs routed, %d cached in total" % (got, len(cache)))
    return cache


# ------------------------------------------------------------------ main ----

STATIONS = os.path.join(DATA, "stations.json")


def load_stations(cfg, warnings):
    """Every MRT station in Singapore, from OneMap, cached in data/stations.json.

    OneMap indexes each station once per exit, so the station records are the
    ones whose name ends in a code in brackets - "CHINATOWN MRT STATION (NE4)".
    An interchange appears once per line and keeps whichever code is nearer;
    both are true answers to "which station is this".
    """
    if os.path.exists(STATIONS):
        return json.load(open(STATIONS))

    pat = re.compile(r"^(.+?) MRT STATION \(([A-Z]{2}\d+(?: */ *[A-Z]{2}\d+)*)\)$")
    base = ("https://www.onemap.gov.sg/api/common/elastic/search?searchVal=MRT+STATION"
            "&returnGeom=Y&getAddrDetails=Y&pageNum=")
    skip = set(cfg.get("mrt_lines_excluded", []))
    found, page = {}, 1
    print("  fetching the MRT network from OneMap (first build only)")
    while True:
        payload = None
        for attempt in range(6):
            try:
                payload = json.load(urllib.request.urlopen(
                    urllib.request.Request(base + str(page),
                        headers={"User-Agent": "food-recommendation refresh"}), timeout=20))
                break
            except Exception:
                time.sleep(1.5 * (attempt + 1))     # OneMap rate-limits a burst
        if payload is None:
            sys.exit("OneMap would not serve page %d of the station list" % page)
        for hit in payload.get("results", []):
            m = pat.match((hit.get("SEARCHVAL") or "").strip())
            if not m:
                continue                            # an exit, not the station
            code = [c.strip() for c in m.group(2).split("/")][0]
            if code in found or code[:2] in skip:
                continue
            found[code] = {"code": code, "line": code[:2], "name": m.group(1).title(),
                           "lat": round(float(hit["LATITUDE"]), 6),
                           "lng": round(float(hit["LONGITUDE"]), 6)}
        if page >= payload.get("totalNumPages", 1):
            break
        page += 1
        time.sleep(0.35)

    if len(found) < 100:
        sys.exit("only %d stations came back - that is not the network, refusing "
                 "to write it" % len(found))
    out = sorted(found.values(), key=lambda s: (s["line"], int(s["code"][2:])))
    write_json(STATIONS, out, indent=1, ensure_ascii=False)
    print("  %d stations cached in data/stations.json" % len(out))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ignore the geocode cache")
    args = ap.parse_args()

    cfg = json.load(open(CONFIG))
    warnings = []

    print("pulling sheet %s ..." % cfg["sheet_id"])
    tabs = read_sheets(download_workbook(cfg["sheet_id"]))

    def is_places(rows):
        return any(v.strip().lower() == "name of place"
                   for cells in rows for v in cells.values())
    places_tabs = [t for t in tabs if is_places(t)]
    if not places_tabs:
        sys.exit('No tab contains a "Name of place" header.')
    places_rows = places_tabs[0]
    homes_rows  = homes_tab(tabs, places_rows, warnings)

    places = parse_places(places_rows, warnings)
    homes  = parse_homes(homes_rows, cfg.get("home_labels", []), warnings)
    print("  %d places, %d homes" % (len(places), len(homes)))

    cache = json.load(open(GEOCACHE)) if os.path.exists(GEOCACHE) else {}
    for rec in places:
        hit = geocode(rec["addr"], cache, warnings, args.force)
        if hit:
            rec.update(lat=hit["lat"], lng=hit["lng"], matched=hit["matched"])
    overrides = cfg.get("home_overrides", {})
    for home in homes:
        postal = home.pop("postal")
        fix = overrides.get(home["name"])
        if fix:
            home.update(lat=fix["lat"], lng=fix["lng"])
            warnings.append("%s: placed from config.home_overrides, not from the "
                            "sheet. %s" % (home["name"], fix.get("why", "")))
            continue
        hit = geocode(postal, cache, warnings, args.force, private=True)
        if hit:
            home.update(lat=hit["lat"], lng=hit["lng"])
            home.pop("matched", None)
        else:
            warnings.append("%s: its code on the sheet does not resolve, so this "
                            "home is NOT on the map. Fix the sheet, or add "
                            "coordinates under home_overrides in config.json."
                            % home["name"])
    # Belt and braces: drop any bare postal-code key an older build cached
    # before home lookups were made private. Place keys are full addresses.
    for key in [k for k in cache if re.fullmatch(r"\d{6}", k)]:
        del cache[key]
    # An address the sheet has dropped is not coming back on its own, and this
    # file is committed to a public repo: the smaller it is, the less there is
    # to leak. Re-geocoding a place that returns costs two calls.
    stale = [k for k in cache if k not in {r["addr"] for r in places}]
    for key in stale:
        del cache[key]
    if stale:
        print("  dropped %d cached geocode%s for addresses no longer on the sheet"
              % (len(stale), "" if len(stale) == 1 else "s"))
    write_json(GEOCACHE, cache, indent=1, sort_keys=True)

    csv_crosscheck(cfg, places, warnings)

    places = [p for p in places if "lat" in p]
    homes  = [h for h in homes if "lat" in h]
    if not places or not homes:
        sys.exit("Nothing geocoded - refusing to write empty data files.")

    # Two different questions, two different lists.
    #
    # "Which station is nearest this place?" is answered against the WHOLE
    # network. It used to be answered against the seven stations drawn on the
    # map, which is fine while every place is in the neighbourhood and wrong
    # the moment one is not: a restaurant in Chinatown came back as Farrer
    # Park, 41 minutes away, because Chinatown was not in the candidate set.
    stations = load_stations(cfg, warnings)
    for rec in places:
        near = min(stations, key=lambda s: haversine(rec, s))
        rec["mrt"] = near["code"]
        rec["mrtD"] = round(haversine(rec, near))

    # "Which station pills does the map draw?" stays the local list - drawing
    # 182 of them would bury the neighbourhood the map exists to show.
    winners = {min(cfg["mrt"], key=lambda s: haversine(pt, s))["code"]
               for pt in places + homes}
    mrt = [s for s in cfg["mrt"] if s["code"] in winners]
    print("  stations drawn: %s" % ", ".join(s["code"] for s in mrt))
    far = [r for r in places if r["mrt"] not in {s["code"] for s in mrt}]
    if far:
        print("  nearest station is off the drawn map for: %s"
              % ", ".join("%s (%s)" % (r["name"], r["mrt"]) for r in far))

    # Label side: west of the pack reads left, east reads right.
    mid = sum(p["lng"] for p in places) / len(places)
    for rec in places:
        rec["dir"] = "right" if rec["lng"] >= mid else "left"
    # A home's label competes with the nearest station's pill more than with
    # anything else on the map, so put it on the far side from that station.
    for home in homes:
        near = min(mrt, key=lambda s: haversine(home, s))
        home["dir"] = "left" if near["lng"] > home["lng"] else "right"

    # Bbox must cover everything drawn, or tiles run out at the edge.
    pad  = cfg.get("bbox_pad_deg", 0.0012)
    lats = [p["lat"] for p in places + homes + mrt]
    lngs = [p["lng"] for p in places + homes + mrt]
    bbox = {"lat0": round(min(lats) - pad, 5), "lat1": round(max(lats) + pad, 5),
            "lng0": round(min(lngs) - pad, 5), "lng1": round(max(lngs) + pad, 5)}
    if bbox != cfg["bbox"]:
        print("  bbox moved -> %s" % bbox)
        cfg["bbox"] = bbox
        write_json(CONFIG, cfg, indent=2)

    # Ids are assigned below, so route lookup happens after them.
    order = ["id", "name", "short", "cat", "by", "lat", "lng", "addr", "price",
             "plus", "minus", "rating", "mrt", "mrtD", "dir", "matched"]
    shorts = cfg.get("short_names", {})
    assign_ids(places, warnings)
    for rec in places:
        rec["short"] = shorts.get(rec["name"]) or shorten(rec["name"])
    places.sort(key=lambda r: (-r["rating"], r["name"]))

    # How long it actually takes, per home, on foot and by train. Keyed the way
    # the page keys it, so the page can look a pair up without knowing anything
    # about how it was fetched.
    routes = travel_times(cfg, homes, places, warnings)
    # routes.json is inlined into index.html whole, so a pair for a place the
    # sheet no longer lists would keep shipping to every viewer for ever.
    live = {"%.5f,%.5f>%.5f,%.5f" % (h["lat"], h["lng"], p["lat"], p["lng"])
            for h in homes for p in places}
    dead = [k for k in routes if k not in live]
    for key in dead:
        del routes[key]
    if dead:
        print("  dropped %d route%s for places no longer on the sheet"
              % (len(dead), "" if len(dead) == 1 else "s"))
    write_json(ROUTES, routes, indent=1, sort_keys=True, ensure_ascii=False)

    write_json(os.path.join(DATA, "places.json"),
               [{k: p[k] for k in order if k in p} for p in places],
               indent=1, ensure_ascii=False)
    write_json(os.path.join(DATA, "homes.json"), homes, indent=1, ensure_ascii=False)
    write_json(os.path.join(DATA, "mrt.json"), mrt, indent=1, ensure_ascii=False)

    print("\nwrote data/places.json, data/homes.json, data/mrt.json, data/routes.json")
    if warnings:
        print("\n%d thing%s worth a look:" % (len(warnings), "" if len(warnings) == 1 else "s"))
        for w in warnings:
            print("  - " + w)
    print("\nNow run:  python3 build/build.py")


if __name__ == "__main__":
    main()
