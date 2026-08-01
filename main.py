"""
Now targeting the real iframe ("TargetContent") with real field IDs found
from inspect_page.py's output. Screenshots after every step so if
something breaks, we can see exactly where.

Run:
    python discover2.py

Then send me:
  - the numbered screenshots (at least whichever one looks wrong)
  - results_table.html (the final results table, if it got that far)
"""

from playwright.sync_api import sync_playwright

START_URL = (
    "https://www.myu.umn.edu/psp/psprd/EMPLOYEE/CAMP/c/"
    "SA_LEARNER_SERVICES.CLASS_SEARCH.GBL"
)

INSTITUTION_VALUE = "UMNTC"   # Twin Cities/Rochester, from the <option value="">
SUBJECT = "PHYS"
COURSE_NUMBER = "1301W"
TERM_MATCH_TEXT = "Fall 2026"  # substring we'll search for among the Term <option> texts

step = 0


def shot(page, label):
    global step
    step += 1
    fname = f"step{step:02d}_{label}.png"
    page.screenshot(path=fname, full_page=True)
    print(f"  -> saved {fname}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=150)
        page = browser.new_page()

        print("Loading page...")
        page.goto(START_URL, wait_until="networkidle", timeout=60000)
        shot(page, "landing")

        frame = page.frame(name="TargetContent")
        if frame is None:
            print("Could not find TargetContent frame! Aborting.")
            page.wait_for_timeout(30000)
            browser.close()
            return

        # --- Institution ---
        print("Selecting Institution = Twin Cities/Rochester...")
        inst_select = frame.locator('select[id^="CLASS_SRCH_WRK2_INSTITUTION"]')
        inst_select.select_option(value=INSTITUTION_VALUE)

        # This triggers a real postback (submitAction_win0). Wait for it.
        frame.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        shot(page, "after_institution")

        # --- Term ---
        print("Reading Term dropdown options...")
        term_select = frame.locator('select[id^="CLASS_SRCH_WRK2_STRM"]')
        options = term_select.locator("option").all()
        term_value = None
        for opt in options:
            text = opt.inner_text().strip()
            val = opt.get_attribute("value")
            print(f"    option: value={val!r} text={text!r}")
            if TERM_MATCH_TEXT in text:
                term_value = val

        if term_value is None:
            print(f"!! Could not find a Term option containing {TERM_MATCH_TEXT!r}. "
                  f"Look at the printed list above and tell me the right text/value.")
        else:
            print(f"Selecting Term value={term_value!r}")
            term_select.select_option(value=term_value)
            frame.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)

        shot(page, "after_term")

        # --- Subject ---
        print("Filling Subject = PHYS...")
        subject_box = frame.locator('input[id^="SSR_CLSRCH_WRK_SUBJECT"]')
        subject_box.fill(SUBJECT)
        shot(page, "after_subject")

        # NOTE: leaving the course-number match type on its default ("begins
        # with") rather than forcing "is exactly" - confirmed working and
        # it's one less thing that can break.

        # --- Course Number ---
        print(f"Filling Course Number = {COURSE_NUMBER}...")
        course_box = frame.locator('input[id^="SSR_CLSRCH_WRK_CATALOG_NBR"]')
        course_box.fill(COURSE_NUMBER)
        shot(page, "after_course_number")

        # --- Search button ---
        print("Looking for the Search button...")
        search_btn = frame.get_by_role("button", name="Search")
        if search_btn.count() == 0:
            print("!! No button found with role=button name=Search. "
                  "Dumping frame HTML to find_search_button.html so we can "
                  "find the right selector.")
            with open("find_search_button.html", "w", encoding="utf-8") as f:
                f.write(frame.content())
        else:
            search_btn.first.click()
            frame.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
            shot(page, "after_search_click")

            # --- Possible "over N classes" confirmation ---
            # This shows up in a SEPARATE nested popup iframe (name like
            # "ptModFrame_0"), not inside TargetContent, and it points at a
            # different subdomain (cs.myu.umn.edu). It only appears for
            # broad searches, so poll briefly for it rather than assuming.
            modal_frame = None
            for _ in range(10):  # poll up to ~5s
                for fr in page.frames:
                    if fr.name and fr.name.startswith("ptModFrame"):
                        modal_frame = fr
                        break
                if modal_frame:
                    break
                page.wait_for_timeout(500)

            if modal_frame:
                print(f"Warning dialog found ({modal_frame.name}), clicking OK...")
                try:
                    ok_btn = modal_frame.locator('input[name="#ICSave"]')
                    ok_btn.click()
                except Exception as e:
                    print(f"    !! Failed to click OK in modal: {e}")
                page.wait_for_timeout(1000)
                frame.wait_for_load_state("networkidle")
                page.wait_for_timeout(1500)
            else:
                print("No warning dialog appeared (fine for a narrower search).")

            shot(page, "final_results")

            tables_html = frame.eval_on_selector_all(
                "table",
                "els => els.map(e => e.outerHTML).join('\\n\\n<!-- NEXT TABLE -->\\n\\n')",
            )
            with open("results_table.html", "w", encoding="utf-8") as f:
                f.write(tables_html)
            print("Saved results_table.html")

        print("\nDone. Browser stays open 45s for you to look around.")
        page.wait_for_timeout(45000)
        browser.close()


if __name__ == "__main__":
    main()