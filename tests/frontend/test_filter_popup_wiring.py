"""Pin the New Jobs **Filter** popup into the served page.

The frontend is one design export (``utils/frontend/templates/index.html``) with no build
step, so the durable guard against regressing it is to assert on the HTML the app actually
serves. These tests encode what the bulk-hide popup must keep:

  * the header Filter button opens the popup rather than firing a pass directly;
  * all four criteria (keyword kill-list, found-before date, match threshold, industries)
    are present and wired to handlers;
  * the dry-run preview is what the commit button promises;
  * the overlay obeys the shared dialog contract (scrim, ``data-overlay``, Esc/Tab trap,
    animated exit) and the accessibility rules in
    ``docs/skills/accessibility-mobile/SKILL.md``.

The browser pane does not composite in this environment, so verification is the served
HTML plus the API tests in ``tests/backend/test_bulk_filter_api.py``.
"""

import re

import pytest

from app import application


@pytest.fixture
def html():
    application.config["TESTING"] = True
    with application.test_client() as c:
        return c.get("/").get_data(as_text=True)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def test_header_filter_button_opens_the_popup(html):
    assert 'onclick="{{ openFilter }}"' in html
    # The old behavior (fire the saved-rules pass straight from the header) is gone.
    assert "{{ filterJobs }}" not in html
    assert "openFilter:()=>this.openFilter()" in html


def test_popup_is_gated_on_its_own_state(html):
    assert '<sc-if value="{{ filterOpen }}"' in html
    assert "filterOpen:false" in html


# --------------------------------------------------------------------------- #
# The four criteria
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("binding", [
    "{{ fltKeywordTags }}",   # keyword kill-list chips
    "{{ onFltKwKey }}",       # Enter adds a term
    "{{ fltScopeList }}",     # title / description scope toggles
    "{{ fltBefore }}",        # found-before date
    "{{ fltDatePresets }}",   # 7 / 14 / 30-day shortcuts
    "{{ fltMinMatch }}",      # match threshold slider
    "{{ toggleFltUnscored }}",  # opt-in for never-analyzed jobs
    "{{ fltIndustryList }}",  # industries present in the feed
])
def test_every_criterion_is_rendered(html, binding):
    assert binding in html


def test_date_input_is_a_native_date_field(html):
    assert re.search(r'id="flt-date"[^>]*type="date"', html)


def test_match_slider_is_a_range_over_the_full_percentage(html):
    assert re.search(r'id="flt-match"[^>]*type="range"[^>]*min="0"[^>]*max="100"', html)


# --------------------------------------------------------------------------- #
# Preview and commit
# --------------------------------------------------------------------------- #

def test_preview_is_a_dry_run_against_the_filter_endpoint(html):
    assert "dry_run:true" in html
    assert "/api/jobs/filter/options" in html


def test_the_commit_button_promises_the_previewed_number(html):
    assert "fltApplyLabel:(s.filterBusy?'Hiding…':(fltActive&&pv?('Hide '+fltMatched+' job'" in html
    assert 'onclick="{{ applyBulkFilter }}"' in html


def test_preview_region_announces_itself(html):
    assert re.search(r'aria-live="polite"[^>]*aria-atomic="true"', html)


def test_debounced_preview_does_not_fire_per_slider_pixel(html):
    assert "schedulePreview(delay)" in html
    assert "delay==null?250:delay" in html


def test_the_saved_rules_pass_is_still_reachable(html):
    assert 'onclick="{{ applySavedRules }}"' in html
    assert "applySavedRules(){" in html


def test_hidden_jobs_are_advertised_as_reversible(html):
    assert "undo with Show Ignored" in html


# --------------------------------------------------------------------------- #
# Overlay + accessibility contract
# --------------------------------------------------------------------------- #

def test_overlay_joins_the_shared_dialog_contract(html):
    assert 'data-overlay="filter"' in html
    assert 'role="dialog" aria-modal="true" aria-labelledby="flt-title"' in html
    assert "else if(name==='filter') this.closeFilter();" in html
    assert "s.findOpen || s.filterOpen ||" in html


def test_overlay_has_an_animated_exit_pair(html):
    assert "fltAnim:ovAnim('filter','jf-pop')" in html
    assert "scrimAnim('filter')" in html
    assert "closeWithExit('filter'" in html


def test_toggles_expose_their_pressed_state(html):
    for binding in ("{{ sk.pressed }}", "{{ dp.pressed }}", "{{ ind.pressed }}",
                    "{{ fltUnscoredPressed }}"):
        assert 'aria-pressed="%s"' % binding in html


def test_labels_are_bound_to_their_controls(html):
    for control in ("flt-kw", "flt-date", "flt-match"):
        assert 'for="%s"' % control in html
        assert 'id="%s"' % control in html


def test_icon_only_close_button_has_an_accessible_name(html):
    assert 'aria-label="Close filter"' in html


def test_primary_touch_targets_meet_the_44px_minimum(html):
    # The date field and both footer actions are primary targets.
    assert 'id="flt-date" type="date" value="{{ fltBefore }}" oninput="{{ onFltBefore }}" style="height:44px' in html
    assert "min-width:150px;height:46px" in html          # commit
    assert "height:46px;padding:0 18px" in html           # re-apply saved rules
