"""
Full pipeline: scrapes UMN's public class search, parses results, diffs
against the last known state, and posts any changes (new sections,
removed sections, or any field changing - status, room, time, instructor)
to a Discord webhook.

Env vars:
    DISCORD_WEBHOOK_URL   (required)  - the webhook URL to post to
    STATE_FILE            (optional)  - defaults to state.json
    DEBUG                 (optional)  - set to "1" to save a screenshot
                                         and the raw results HTML on each run

To monitor a different course/term, only the CONFIG block below needs
to change.
"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from parser import parse_sections, filter_sections  # filter_sections kept available, unused by default now

# ----------------------------- CONFIG ---------------------------------
START_URL = (
    "https://www.myu.umn.edu/psp/psprd/EMPLOYEE/CAMP/c/"
    "SA_LEARNER_SERVICES.CLASS_SEARCH.GBL"
)
INSTITUTION_VALUE = "UMNTC"      # Twin Cities/Rochester
SUBJECT = "PHYS"
COURSE_NUMBER = "1301W"
TERM_MATCH_TEXT = "Fall 2026"    # substring to find in the Term dropdown

# ------------------------------------------------------------------------
# Tracking ALL sections/components (lecture, lab, discussion, etc.) - no
# filtering. If you ever want to narrow it back down to e.g. just labs
# numbered 4xx, use filter_sections() from parser.py on `all_sections`
# below before diffing.

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DEBUG = os.environ.get("DEBUG") == "1"


def scrape() -> str:
    """Runs the search and returns the raw results table HTML."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not DEBUG)
        page = browser.new_page()
        page.goto(START_URL, wait_until="networkidle", timeout=60000)

        frame = page.frame(name="TargetContent")
        if frame is None:
            raise RuntimeError("Could not find TargetContent frame")

        inst_select = frame.locator('select[id^="CLASS_SRCH_WRK2_INSTITUTION"]')
        inst_select.select_option(value=INSTITUTION_VALUE)
        frame.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        term_select = frame.locator('select[id^="CLASS_SRCH_WRK2_STRM"]')
        term_value = None
        for opt in term_select.locator("option").all():
            if TERM_MATCH_TEXT in opt.inner_text():
                term_value = opt.get_attribute("value")
                break
        if term_value is None:
            raise RuntimeError(f"Could not find Term option containing {TERM_MATCH_TEXT!r}")
        term_select.select_option(value=term_value)
        frame.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        frame.locator('input[id^="SSR_CLSRCH_WRK_SUBJECT"]').fill(SUBJECT)
        frame.locator('input[id^="SSR_CLSRCH_WRK_CATALOG_NBR"]').fill(COURSE_NUMBER)

        search_btn = frame.get_by_role("button", name="Search")
        search_btn.first.click()
        frame.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Handle the "over N classes" confirmation if it appears - lives in
        # a separate nested popup iframe, not the TargetContent frame.
        modal_frame = None
        for _ in range(10):
            for fr in page.frames:
                if fr.name and fr.name.startswith("ptModFrame"):
                    modal_frame = fr
                    break
            if modal_frame:
                break
            page.wait_for_timeout(500)

        if modal_frame:
            modal_frame.locator('input[name="#ICSave"]').click()
            page.wait_for_timeout(1000)
            frame.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)

        if DEBUG:
            page.screenshot(path="debug_final.png", full_page=True)

        tables_html = frame.eval_on_selector_all(
            "table",
            "els => els.map(e => e.outerHTML).join('\\n')",
        )

        if DEBUG:
            Path("debug_results.html").write_text(tables_html, encoding="utf-8")

        browser.close()
        return tables_html


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
                # explicitly allow the @everyone mention to actually ping -
                # Discord requires this be opted into per-message, otherwise
                # "@everyone" is sent as inert plain text
                "allowed_mentions": {"parse": ["everyone"]},
            },
        )
        resp.raise_for_status()


def main():
    print(f"Scraping PHYS {COURSE_NUMBER}, term matching {TERM_MATCH_TEXT!r}...")
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