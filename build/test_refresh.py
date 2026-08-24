#!/usr/bin/env python3
"""Unit tests for build/refresh.py - the sheet reader, not the page.

    python3 build/test_refresh.py

build/smoke.py exercises the built page's JavaScript. Nothing exercised the
Python until now, which is why both of this file's real bugs lived for weeks:

  * a self-closing <c r="E5" s="1"/> made a blank Minus swallow the Rating in
    the cell beside it, so ratings landed in the wrong field
  * a "rescue" that moved a stray number from Minus into Rating hid that, and
    made a parser bug look like a habit of whoever edits the sheet

Both are invisible from the page: the map still drew, the table still filled.
Each is one assertion here.
"""
import io, os, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refresh


# ------------------------------------------------------------- fixtures ----

class S(str):
    """A cell whose value goes through the shared-string table, as text does."""


def workbook(tabs):
    """tabs: [[ {"A": value, ...}, ...rows ], ...].

    A value of None is written the way Excel writes an empty-but-styled cell -
    self-closing, with no </c> of its own - which is the shape that broke the
    reader once.
    """
    shared, index = [], {}

    def strid(word):
        if word not in index:
            index[word] = len(shared)
            shared.append(word)
        return index[word]

    sheets = []
    for rows in tabs:
        body = ""
        for n, cells in enumerate(rows, 1):
            row = ""
            for col in sorted(cells):
                val = cells[col]
                ref = "%s%d" % (col, n)
                if val is None:
                    row += '<c r="%s" s="1"/>' % ref
                elif isinstance(val, S):
                    row += '<c r="%s" t="s"><v>%d</v></c>' % (ref, strid(str(val)))
                else:
                    row += '<c r="%s"><v>%s</v></c>' % (ref, val)
            body += "<row>%s</row>" % row
        sheets.append("<worksheet><sheetData>%s</sheetData></worksheet>" % body)

    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as z:
        z.writestr("xl/sharedStrings.xml",
                   "<sst>%s</sst>" % "".join("<si><t>%s</t></si>" % w for w in shared))
        for i, xml in enumerate(sheets, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, xml)
    return blob.getvalue()


def tabs_of(*tabs):
    return refresh.read_sheets(workbook(list(tabs)))


ADDR = S("20 Keong Saik Rd, Singapore 089126")
FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append("%s\n     got:  %r\n     want: %r" % (name, got, want))


# ---------------------------------------------------------------- tests ----

def test_self_closing_cell_does_not_steal_the_next_value():
    """The regression: an empty-but-styled Minus must not eat the Rating."""
    rows = [{"A": S("Name of place"), "B": S("Minus"),
             "C": S("Rating"), "D": S("Address")},
            {"A": S("Char"), "B": None, "C": "4.5", "D": ADDR}]
    got = tabs_of(rows)[0][1]
    check("the rating stays in its own column", got.get("C"), "4.5")
    check("the empty cell stays empty", "B" in got, False)

    warnings = []
    places = refresh.parse_places(tabs_of(rows)[0], warnings)
    check("and the place is rated", places[0]["rating"], 4.5)
    check("with nothing to rescue", places[0]["minus"], "")


def test_header_is_found_wherever_it_drifts():
    rows = [{"A": S("some note somebody left")},
            {"A": S("Name of place"), "B": S("Rating"), "C": S("Address")},
            {"A": S("Char"), "B": "4.5", "C": ADDR}]
    start, cols = refresh.find_header(tabs_of(rows)[0])
    check("header found below the stray line", start, 1)
    check("name column mapped", cols.get("A"), "name")
    check("address column mapped", cols.get("C"), "addr")


def test_columns_are_matched_by_text_not_position():
    rows = [{"A": S("Rating"), "B": S("Name of place"), "C": S("Link / Address")},
            {"A": "4.5", "B": S("Char"), "C": ADDR}]
    warnings = []
    places = refresh.parse_places(tabs_of(rows)[0], warnings)
    check("one place parsed from reordered columns", len(places), 1)
    check("name read from the middle column", places[0]["name"], "Char")
    check("rating read from the first column", places[0]["rating"], 4.5)


def test_a_rating_that_is_not_a_number_says_so():
    rows = [{"A": S("Name of place"), "B": S("Rating"), "C": S("Address")},
            {"A": S("Char"), "B": S("lovely"), "C": ADDR}]
    warnings = []
    places = refresh.parse_places(tabs_of(rows)[0], warnings)
    check("unrated rather than crashed", places[0]["rating"], 0.0)
    check("and it says so", any("not a number" in w for w in warnings), True)


def test_homes_come_from_the_tab_that_says_postal_code():
    food = [{"A": S("Name of place"), "B": S("Address")},
            {"A": S("Char"), "B": ADDR}]
    homes = [{"B": S("Insert your house postal code below")},
             {"B": S("Someone's house"), "C": "330008"}]
    tabs = tabs_of(homes, food)                      # homes tab FIRST, on purpose
    warnings = []
    food_tab = next(t for t in tabs
                    if any(v == "Name of place" for c in t for v in c.values()))
    got = refresh.parse_homes(refresh.homes_tab(tabs, food_tab, warnings),
                              ["A's Hse"], warnings)
    check("the labelled tab wins whatever the tab order",
          [h["name"] for h in got], ["A's Hse"])
    check("so no fallback was needed",
          any("not the food list" in w for w in warnings), False)


def test_an_unlabelled_second_tab_still_works_but_complains():
    food = [{"A": S("Name of place"), "B": S("Address")},
            {"A": S("Char"), "B": ADDR}]
    homes = [{"B": S("Someone's house"), "C": "330008"}]
    tabs = tabs_of(food, homes)
    warnings = []
    food_tab = tabs[0]
    got = refresh.parse_homes(refresh.homes_tab(tabs, food_tab, warnings),
                              ["A's Hse"], warnings)
    check("it still finds the home", [h["name"] for h in got], ["A's Hse"])
    check("and asks for a heading",
          any("not the food list" in w for w in warnings), True)


def test_a_stray_six_digit_number_is_not_a_front_door():
    # The stray sits to the LEFT of the real code, so a reader that takes the
    # first six-digit cell in the row picks the wrong one and this test says so.
    rows = [{"A": S("Insert your house postal code below")},
            {"A": S("Someone's house"), "B": "123456", "C": "330008"},
            {"A": S("Another's house"), "C": "339511"}]
    tab = tabs_of(rows)[0]
    warnings = []
    got = refresh.parse_homes(tab, ["A's Hse", "B's Hse"], warnings)
    check("column C holds the codes", refresh.postal_column(tab), "C")
    check("one home per row, read from that column",
          [h["name"] for h in got], ["A's Hse", "B's Hse"])
    check("and the stray number was not geocoded",
          [h["postal"] for h in got], ["330008", "339511"])


def test_the_sheets_own_label_is_never_published():
    # The sheet names these rows after the people who live in them. Whatever it
    # says, the page shows the config label for that position and nothing else -
    # including in the warnings, which are printed into a public Actions log.
    rows = [{"A": S("Insert your house postal code below")},
            {"A": S("Real Person hse"), "B": "330008"},
            {"A": S("Another Real Person hse"), "B": "339511"},
            {"A": S("A Third Real Person hse"), "B": "408866"}]
    warnings = []
    got = refresh.parse_homes(tabs_of(rows)[0], ["A's Hse", "B's Hse"], warnings)
    check("labelled from config, in tab order",
          [h["name"] for h in got], ["A's Hse", "B's Hse", "Home 3"])
    check("a home with no label in config says so",
          any("no name in config.home_labels" in w for w in warnings), True)
    check("and no sheet label reaches a name or a warning",
          any("Real Person" in t
              for t in [h["name"] for h in got] + warnings), False)


def test_two_long_names_do_not_share_an_id():
    long_a = "Ju Xing Hainanese Boneless Chicken Rice Geylang Bahru"
    long_b = "Ju Xing Hainanese Boneless Chicken Rice Chinatown"
    check("the two names do truncate alike", long_a[:28], long_b[:28])
    places = [{"name": long_a}, {"name": long_b}]
    warnings = []
    refresh.assign_ids(places, warnings)
    check("but the ids differ", places[0]["id"] != places[1]["id"], True)
    check("and it says so", any("another place already has" in w for w in warnings), True)


def test_ordinary_names_keep_a_readable_id():
    places = [{"name": "Ah Ong Hokkien Mee"}, {"name": "Char"}]
    refresh.assign_ids(places, [])
    check("id is the slug", [p["id"] for p in places], ["ah-ong-hokkien-mee", "char"])


def test_shorten_cuts_on_a_word():
    check("long name cut at a word",
          refresh.shorten("88 Hong Kong Roast Meat Specialist"), "88 Hong Kong Roast Meat…")
    check("venue tail dropped", refresh.shorten("A Hot Hideout @ Lavender"), "A Hot Hideout")
    check("short name untouched", refresh.shorten("Char"), "Char")


# ----------------------------------------------------------------- main ----

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            FAILURES.append("%s raised %s: %s" % (fn.__name__, type(exc).__name__, exc))
    if FAILURES:
        print("REFRESH TESTS FAILED")
        for f in FAILURES:
            print("  - " + f)
        sys.exit(1)
    print("refresh tests passed - %d cases over the sheet reader" % len(tests))


if __name__ == "__main__":
    main()
