"""
Parses the PeopleSoft public class search results HTML into a list of
full section records, deduplicated (the raw HTML contains each section's
markup multiple times because of nested <table> elements - not a data
issue, just how nested outerHTML works).

Test offline:
    python parser.py results_table.html
"""

import re
import sys
from bs4 import BeautifulSoup

CLASS_NBR_RE = re.compile(r"^win0divMTG_CLASS_NBR\$(\d+)$")

# PeopleSoft's ICAJAX=1 responses wrap the real page content as escaped text
# inside a CDATA block: <FIELD id='win0divPAGECONTAINER'><![CDATA[ ...actual
# HTML... ]]></FIELD>. Python's html.parser has no defined behavior for CDATA
# sections (not valid HTML syntax), so asking it to parse straight through
# one is undefined/inconsistent - it happened to recover correctly once and
# silently failed the next time. Pulling the real HTML out as plain text
# first, before handing it to BeautifulSoup, removes that ambiguity entirely.
PAGECONTAINER_CDATA_RE = re.compile(
    r"<FIELD id='win0divPAGECONTAINER'><!\[CDATA\[(.*?)\]\]></FIELD>",
    re.DOTALL,
)


def _unwrap_cdata(html: str) -> str:
    m = PAGECONTAINER_CDATA_RE.search(html)
    return m.group(1) if m else html  # fall back to raw input if not wrapped
    # (e.g. a plain, non-AJAX HTML page - keeps this working either way)


def _text(soup, id_, sep=" "):
    el = soup.find(id=id_)
    if el is None:
        return None
    return el.get_text(separator=sep, strip=True)


def parse_sections(html: str) -> list[dict]:
    html = _unwrap_cdata(html)
    soup = BeautifulSoup(html, "html.parser")
    seen_class_nbrs = set()
    records = []

    for div in soup.find_all(id=CLASS_NBR_RE):
        idx = CLASS_NBR_RE.match(div["id"]).group(1)

        class_nbr_a = div.find("a")
        class_nbr = class_nbr_a.get_text(strip=True) if class_nbr_a else None
        if not class_nbr or class_nbr in seen_class_nbrs:
            continue  # dedup - nested tables repeat the same section

        name_div = soup.find(id=f"win0divMTG_CLASSNAME${idx}")
        if name_div is None:
            continue
        name_a = name_div.find("a")
        raw_name = name_a.get_text(separator="|", strip=True) if name_a else ""
        section_part = raw_name.split("|")[0] if raw_name else ""

        m = re.match(r"^(\d+)-(\w+)$", section_part)
        if not m:
            continue
        section_number, component = m.group(1), m.group(2)

        status_div = soup.find(id=f"win0divDERIVED_CLSRCH_SSR_STATUS_LONG${idx}")
        status = None
        if status_div:
            img = status_div.find("img")
            if img and img.get("alt"):
                status = img["alt"].strip()

        days_times = _text(soup, f"MTG_DAYTIME${idx}", sep=" / ")
        room = _text(soup, f"MTG_ROOM${idx}", sep=" / ")
        instructor = _text(soup, f"MTG_INSTR${idx}", sep=" / ")
        meeting_dates = _text(soup, f"MTG_TOPIC${idx}", sep=" / ")

        seen_class_nbrs.add(class_nbr)
        records.append({
            "class_nbr": class_nbr,
            "section_number": section_number,
            "component": component,
            "days_times": days_times,
            "room": room,
            "instructor": instructor,
            "meeting_dates": meeting_dates,
            "status": status,
        })

    records.sort(key=lambda r: (r["component"], int(r["section_number"])))
    return records


def filter_sections(sections: list[dict], component: str, number_prefix: str) -> list[dict]:
    """e.g. filter_sections(all, component='LAB', number_prefix='4')
    matches "Laboratory Section 4xx"."""
    return [
        s for s in sections
        if s["component"].upper() == component.upper()
        and s["section_number"].startswith(number_prefix)
    ]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parser.py <path to results_table.html>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        html = f.read()

    all_sections = parse_sections(html)
    print(f"Found {len(all_sections)} unique classes:\n")
    for s in all_sections:
        print(f"  {s['section_number']}-{s['component']:5s}  class_nbr={s['class_nbr']:6s}  "
              f"status={s['status']:10s}  {s['days_times']}  |  {s['room']}  |  {s['instructor']}")

    lab_count = sum(
        1 for s in all_sections
        if s["component"].upper() == "LAB" and s["section_number"].startswith("4")
    )
    print(f"\nFiltered to Laboratory Section 4xx ({lab_count} found):\n")
    labs = filter_sections(all_sections, component="LAB", number_prefix="4")
    for s in labs:
        print(f"  Laboratory Section {s['section_number']}  class_nbr={s['class_nbr']}  status={s['status']}")