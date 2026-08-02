"""
EXPERIMENTAL: raw requests version, no browser.

Tests a hypothesis: since selecting Institution alone auto-filled Term to
the current/default term (per your Burp trace), maybe we don't need to
replay the individual Institution-select and Term-select postbacks at all -
maybe we can jump straight from the initial page load to one POST with
Institution + Term + Subject + Catalog Nbr already filled in, using
ICAction=CLASS_SRCH_WRK2_SSR_PB_CLASS_SRCH (the Search button action).

This is a genuine unknown - PeopleSoft's server-side state machine might
reject a "jump" like this if it expects the intermediate steps to have
already run server-side. This script is built to fail loudly and dump
every response to disk so we can see exactly where/why if it doesn't work.

Run:
    pip install requests beautifulsoup4
    python raw_request_test.py

Then send me: everything printed to the terminal, plus whichever numbered
.html file corresponds to a failure.
"""

import re
import requests
from bs4 import BeautifulSoup

INSTITUTION_VALUE = "UMNTC"
TERM_VALUE = "1269"       # Fall 2026, confirmed from your capture
SUBJECT = "PHYS"
COURSE_NUMBER = "1301W"

START_URL = "https://www.myu.umn.edu/psp/psprd/EMPLOYEE/CAMP/c/SA_LEARNER_SERVICES.CLASS_SEARCH.GBL"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def dump(name, resp):
    fname = f"raw_{name}.html"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(resp.text)
    print(f"  [saved {fname}]  status={resp.status_code}  final_url={resp.url}")


def extract_hidden_field(html: str, name: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.find("input", attrs={"name": name})
    return el.get("value") if el else None


def find_iframe_src(html: str, iframe_name: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    frame = soup.find("iframe", attrs={"name": iframe_name})
    if frame is None:
        # sometimes it's an id instead of/as well as name
        frame = soup.find("iframe", attrs={"id": iframe_name})
    return frame.get("src") if frame else None


def main():
    print("Step 1: GET start URL (following redirects)...")
    resp = session.get(START_URL, headers={**HEADERS, "Sec-Fetch-Mode": "navigate"}, allow_redirects=True, timeout=30)
    dump("1_start", resp)

    print("\nStep 2: looking for TargetContent iframe in the response...")
    iframe_src = find_iframe_src(resp.text, "TargetContent")
    if iframe_src is None:
        print("  !! No TargetContent iframe found. The redirect chain may not "
              "have landed where expected. Check raw_1_start.html manually - "
              "search for 'iframe' and tell me what you find.")
        return
    print(f"  Found iframe src: {iframe_src}")

    print("\nStep 3: GET the iframe content (the actual search form)...")
    resp2 = session.get(iframe_src, headers={**HEADERS, "Referer": resp.url}, timeout=30)
    dump("2_form", resp2)

    ic_state_num = extract_hidden_field(resp2.text, "ICStateNum")
    ic_sid = extract_hidden_field(resp2.text, "ICSID")
    print(f"  ICStateNum={ic_state_num!r}  ICSID={'<found>' if ic_sid else None}")

    if ic_state_num is None or ic_sid is None:
        print("  !! Could not find ICStateNum/ICSID hidden fields. Check "
              "raw_2_form.html for the actual field names/format - they "
              "might not match the exact regex pattern I guessed.")
        return

    print("\nStep 4: attempting to jump straight to Search with all fields "
          "filled at once (skipping individual dropdown postbacks)...")

    form_data = {
        "ICAJAX": "1",
        "ICNAVTYPEDROPDOWN": "0",
        "ICType": "Panel",
        "ICElementNum": "0",
        "ICStateNum": ic_state_num,
        "ICAction": "CLASS_SRCH_WRK2_SSR_PB_CLASS_SRCH",
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

    post_headers = {
        **HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://cs.myu.umn.edu",
        "Referer": resp2.url,
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }

    resp3 = session.post(iframe_src.split("?")[0], data=form_data, headers=post_headers, timeout=30)
    dump("3_search_result", resp3)

    if "SSR_CLSRCH_MTG1" in resp3.text:
        print("\n  SUCCESS: results table marker found directly! The jump worked "
              "and no warning appeared this time.")
        return

    is_warning = "#ICSave" in resp3.text and "PSPUSHBUTTONTBOK" in resp3.text
    if not is_warning:
        print("\n  Unclear result - didn't find the results table marker or the "
              "OK/Cancel warning buttons. Check raw_3_search_result.html manually.")
        return

    print("\n  Confirmed: warning/confirmation page (as expected for a broad "
          "search). Proceeding to click OK...")

    print("\nStep 5: clicking OK on the warning (ICAction=#ICSave)...")
    new_state_num = extract_hidden_field(resp3.text, "ICStateNum")
    new_sid = extract_hidden_field(resp3.text, "ICSID")
    print(f"  new ICStateNum={new_state_num!r}  new ICSID={'<found>' if new_sid else None}")

    if new_state_num is None or new_sid is None:
        print("  !! Could not find updated ICStateNum/ICSID on the warning page. "
              "Check raw_3_search_result.html for the actual hidden field values.")
        return

    ok_form_data = dict(form_data)  # resubmit the same filled-in form...
    ok_form_data["ICStateNum"] = new_state_num
    ok_form_data["ICSID"] = new_sid
    ok_form_data["ICAction"] = "#ICSave"  # ...but this time signal the OK click

    resp4 = session.post(iframe_src.split("?")[0], data=ok_form_data, headers=post_headers, timeout=30)
    dump("4_after_ok", resp4)

    if "SSR_CLSRCH_MTG1" in resp4.text:
        print("\n  SUCCESS: results table found after clicking OK! Full chain "
              "confirmed: 1 GET (bootstrap) -> 1 GET (form) -> 1 POST (search, "
              "all fields at once) -> 1 POST (OK click) -> results.")
    else:
        print("\n  Still no results table marker. Check raw_4_after_ok.html - "
              "might need a different ICAction value, or the OK click might "
              "need different accompanying fields than a full form resubmit.")


if __name__ == "__main__":
    main()