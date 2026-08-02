"""
Full pipeline, raw-requests version (no browser needed): scrapes UMN's
public class search via the 4-request chain we reverse-engineered
(bootstrap GET -> form GET -> search POST -> OK-click POST), parses
results, diffs against the last known state, and posts any changes (new
sections, removed sections, or any field changing - status, room, time,
instructor) to a Discord webhook.

Env vars:
    DISCORD_WEBHOOK_URL   (required)  - the webhook URL to post to
    STATE_FILE            (optional)  - defaults to state.json

To monitor a different course, change SUBJECT/COURSE_NUMBER below.

IMPORTANT: TERM_VALUE is a hardcoded PeopleSoft term code (1269 = Fall
2026), NOT auto-detected. This is the one thing you MUST update by hand
each semester, since skipping the Term dropdown entirely is what makes
this fast. If results start looking stale/empty, this is the first thing
to check. Find the new code the same way we found this one: intercept a
real search in Burp/browser devtools and read
CLASS_SRCH_WRK2_STRM$35$=<value> from the POST body.
"""

import json
import os
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from parser import parse_sections

# ----------------------------- CONFIG ---------------------------------
START_URL = (
    "https://www.myu.umn.edu/psp/psprd/EMPLOYEE/CAMP/c/"
    "SA_LEARNER_SERVICES.CLASS_SEARCH.GBL"
)
INSTITUTION_VALUE = "UMNTC"      # Twin Cities/Rochester
SUBJECT = "PHYS"
COURSE_NUMBER = "1301W"
TERM_VALUE = "1269"              # Fall 2026 - SEE WARNING ABOVE, update each semester
# ------------------------------------------------------------------------

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DEBUG = os.environ.get("DEBUG") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _extract_hidden_field(html: str, name: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.find("input", attrs={"name": name})
    return el.get("value") if el else None


def _find_iframe_src(html: str, iframe_name: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    frame = soup.find("iframe", attrs={"name": iframe_name})
    if frame is None:
        frame = soup.find("iframe", attrs={"id": iframe_name})
    return frame.get("src") if frame else None


def _build_search_form(ic_state_num: str, ic_sid: str, ic_action: str) -> dict:
    """The full PeopleSoft form payload. Same shape whether we're clicking
    Search or clicking OK on the confirmation - only ICStateNum, ICSID, and
    ICAction change between the two."""
    return {
        "ICAJAX": "1",
        "ICNAVTYPEDROPDOWN": "0",
        "ICType": "Panel",
        "ICElementNum": "0",
        "ICStateNum": ic_state_num,
        "ICAction": ic_action,
        "ICModelCancel": "0",
        "ICXPos": "0",
        "ICYPos": "252",
        "ResponsetoDiffFrame": "-1",
        "TargetFrameName": "None",
        "FacetPath": "None",
        "TA_BuildChoices": "1",
        "SP_FldName": "",
        "SP_FldValues": "",
        "PrmtTbl": "",
        "PrmtTbl_fn": "",
        "PrmtTbl_fv": "",
        "TA_SkipFldNms": "",
        "ICFocus": "",
        "ICSaveWarningFilter": "0",
        "ICChanged": "-1",
        "ICSkipPending": "0",
        "ICAutoSave": "0",
        "ICResubmit": "0",
        "ICSID": ic_sid,
        "ICActionPrompt": "false",
        "EnableSmartPrompt": "0",
        "EnableSmartSelect": "0",
        "ICBcDomData": "UnknownValue",
        "ICPanelName": "",
        "ICFind": "",
        "ICAddCount": "",
        "ICAppClsData": "",
        "CLASS_SRCH_WRK2_INSTITUTION$31$": INSTITUTION_VALUE,
        "CLASS_SRCH_WRK2_STRM$35$": TERM_VALUE,
        "SSR_CLSRCH_WRK_SUBJECT$0": SUBJECT,
        "SSR_CLSRCH_WRK_SSR_EXACT_MATCH1$1": "E",
        "SSR_CLSRCH_WRK_CATALOG_NBR$1": COURSE_NUMBER,
        "SSR_CLSRCH_WRK_ACAD_CAREER$2": "",
        "SSR_CLSRCH_WRK_SESSION_CODE$3": "",
        "SSR_CLSRCH_WRK_CAMPUS$4": "",
        "SSR_CLSRCH_WRK_CRSE_ATTR$5": "",
        "SSR_CLSRCH_WRK_CRSE_ATTR_VALUE$5": "",
        "SSR_CLSRCH_WRK_SSR_OPEN_ONLY$chk$6": "N",
        "SSR_CLSRCH_WRK_SSR_START_TIME_OPR$7": "GE",
        "SSR_CLSRCH_WRK_MEETING_TIME_START$7": "",
        "SSR_CLSRCH_WRK_SSR_END_TIME_OPR$7": "LE",
        "SSR_CLSRCH_WRK_MEETING_TIME_END$7": "",
        "SSR_CLSRCH_WRK_INCLUDE_CLASS_DAYS$8": "I",
        "SSR_CLSRCH_WRK_SUN$chk$8": "",
        "SSR_CLSRCH_WRK_MON$chk$8": "",
        "SSR_CLSRCH_WRK_TUES$chk$8": "",
        "SSR_CLSRCH_WRK_WED$chk$8": "",
        "SSR_CLSRCH_WRK_THURS$chk$8": "",
        "SSR_CLSRCH_WRK_FRI$chk$8": "",
        "SSR_CLSRCH_WRK_SAT$chk$8": "",
        "SSR_CLSRCH_WRK_SSR_EXACT_MATCH2$9": "B",
        "SSR_CLSRCH_WRK_LAST_NAME$9": "",
        "SSR_CLSRCH_WRK_CLASS_NBR$10": "",
        "SSR_CLSRCH_WRK_DESCR$11": "",
        "SSR_CLSRCH_WRK_SSR_UNITS_MIN_OPR$12": "GE",
        "SSR_CLSRCH_WRK_UNITS_MINIMUM$12": "",
        "SSR_CLSRCH_WRK_SSR_UNITS_MAX_OPR$12": "LE",
        "SSR_CLSRCH_WRK_UNITS_MAXIMUM$12": "",
        "SSR_CLSRCH_WRK_SSR_COMPONENT$13": "",
        "SSR_CLSRCH_WRK_INSTRUCTION_MODE$14": "",
        "SSR_CLSRCH_WRK_LOCATION$15": "",
    }


def scrape() -> str:
    """Runs the 4-request chain and returns the final results page HTML."""
    session = requests.Session()
    session.headers.update(HEADERS)

    resp1 = session.get(START_URL, allow_redirects=True, timeout=30)
    if DEBUG:
        Path("debug_1_start.html").write_text(resp1.text, encoding="utf-8")

    iframe_src = _find_iframe_src(resp1.text, "TargetContent")
    if iframe_src is None:
        raise RuntimeError("Could not find TargetContent iframe on bootstrap page")

    resp2 = session.get(iframe_src, headers={"Referer": resp1.url}, timeout=30)
    if DEBUG:
        Path("debug_2_form.html").write_text(resp2.text, encoding="utf-8")

    ic_state_num = _extract_hidden_field(resp2.text, "ICStateNum")
    ic_sid = _extract_hidden_field(resp2.text, "ICSID")
    if ic_state_num is None or ic_sid is None:
        raise RuntimeError("Could not find ICStateNum/ICSID on the search form page")

    post_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://cs.myu.umn.edu",
        "Referer": resp2.url,
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }
    search_url = iframe_src.split("?")[0]

    search_form = _build_search_form(ic_state_num, ic_sid, "CLASS_SRCH_WRK2_SSR_PB_CLASS_SRCH")
    resp3 = session.post(search_url, data=search_form, headers=post_headers, timeout=30)
    if DEBUG:
        Path("debug_3_search.html").write_text(resp3.text, encoding="utf-8")

    if "SSR_CLSRCH_MTG1" in resp3.text:
        return resp3.text  # no confirmation dialog this time - done

    is_warning = "#ICSave" in resp3.text and "PSPUSHBUTTONTBOK" in resp3.text
    if not is_warning:
        raise RuntimeError(
            "Search response was neither results nor the expected warning page. "
            "UMN may have changed something - run with DEBUG=1 and inspect "
            "debug_3_search.html."
        )

    new_state_num = _extract_hidden_field(resp3.text, "ICStateNum")
    new_sid = _extract_hidden_field(resp3.text, "ICSID")
    if new_state_num is None or new_sid is None:
        raise RuntimeError("Could not find updated ICStateNum/ICSID on the warning page")

    ok_form = _build_search_form(new_state_num, new_sid, "#ICSave")
    resp4 = session.post(search_url, data=ok_form, headers=post_headers, timeout=30)
    if DEBUG:
        Path("debug_4_after_ok.html").write_text(resp4.text, encoding="utf-8")

    if "SSR_CLSRCH_MTG1" not in resp4.text:
        raise RuntimeError(
            "Still no results table after clicking OK. Run with DEBUG=1 and "
            "inspect debug_4_after_ok.html."
        )

    return resp4.text


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(sections: list[dict]) -> None:
    by_class_nbr = {s["class_nbr"]: s for s in sections}
    STATE_FILE.write_text(json.dumps(by_class_nbr, indent=2), encoding="utf-8")


FIELDS_TO_COMPARE = ["section_number", "component", "days_times", "room", "instructor", "meeting_dates", "status"]


def diff_sections(old: dict, new_sections: list[dict]) -> list[str]:
    """Returns a list of human-readable change lines."""
    lines = []
    new_by_nbr = {s["class_nbr"]: s for s in new_sections}

    added = [nbr for nbr in new_by_nbr if nbr not in old]
    removed = [nbr for nbr in old if nbr not in new_by_nbr]
    common = [nbr for nbr in new_by_nbr if nbr in old]

    for nbr in added:
        s = new_by_nbr[nbr]
        lines.append(
            f"🟢 **NEW** section {s['section_number']}-{s['component']} "
            f"(class {nbr}) — status **{s['status']}** — {s['days_times']} — "
            f"{s['room']} — {s['instructor']}"
        )

    for nbr in removed:
        s = old[nbr]
        lines.append(
            f"🔴 **REMOVED** section {s['section_number']}-{s['component']} "
            f"(class {nbr}) — last known status was {s['status']}"
        )

    for nbr in common:
        old_s, new_s = old[nbr], new_by_nbr[nbr]
        changed_fields = [f for f in FIELDS_TO_COMPARE if old_s.get(f) != new_s.get(f)]
        if changed_fields:
            parts = ", ".join(
                f"{f} `{old_s.get(f)}` → `{new_s.get(f)}`" for f in changed_fields
            )
            lines.append(
                f"🔄 Section {new_s['section_number']}-{new_s['component']} "
                f"(class {nbr}): {parts}"
            )

    return lines


def send_discord(lines: list[str]) -> None:
    if lines:
        header = f"**@everyone {SUBJECT} {COURSE_NUMBER} — section changes detected:**\n"
        message = header + "\n".join(lines)
    else:
        message = f"✅ {SUBJECT} {COURSE_NUMBER} monitor ran, no changes since last poll."

    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL not set - skipping notification. Message would have been:")
        print(message)
        return

    # Discord's hard limit is 2000 chars per message; split if needed.
    chunks = []
    while message:
        if len(message) <= 2000:
            chunks.append(message)
            break
        split_at = message.rfind("\n", 0, 2000)
        if split_at == -1:
            split_at = 2000
        chunks.append(message[:split_at])
        message = message[split_at:]

    for chunk in chunks:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": chunk,
                "allowed_mentions": {"parse": ["everyone"]},
            },
        )
        resp.raise_for_status()


def main():
    print(f"Scraping {SUBJECT} {COURSE_NUMBER}, term {TERM_VALUE}...")
    html = scrape()

    all_sections = parse_sections(html)
    print(f"Parsed {len(all_sections)} unique classes. Tracking all of them.")

    old_state = load_state()
    changes = diff_sections(old_state, all_sections)

    if changes:
        print(f"{len(changes)} change(s) detected:")
        for l in changes:
            print("  " + l)
    else:
        print("No changes since last poll.")

    send_discord(changes)
    save_state(all_sections)


if __name__ == "__main__":
    main()