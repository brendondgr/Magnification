"""Pin the loading ladder and motion contract of the served page.

The frontend is one design export (``utils/frontend/templates/index.html``), so the
only durable guard against regressing it is to assert on the HTML the app actually
serves. These tests encode the non-negotiables from ``docs/frontend-polish-spec.md``:

  * every async region has idle / loading / success / error / empty states
  * no indicator renders for a wait under 300ms, and no skeleton loops forever
  * skeletons trace the real card and carry the right ARIA
  * durations and easings come from tokens, not hardcoded literals
  * ``prefers-reduced-motion`` is honoured, and hover never sticks on touch
"""

import re
from pathlib import Path

import pytest

from app import application

RUNTIME_JS = (
    Path(__file__).resolve().parents[2]
    / "utils" / "frontend" / "static" / "js" / "dc-runtime.js"
)


@pytest.fixture
def html():
    application.config["TESTING"] = True
    with application.test_client() as c:
        return c.get("/").get_data(as_text=True)


# --------------------------------------------------------------------------- #
# The 300ms delay gate and the skeleton timeout (§3)
# --------------------------------------------------------------------------- #

def test_delay_gate_and_timeout_constants(html):
    """A wait under 300ms shows nothing; a wait over 15s becomes an error."""
    assert "static SKELETON_DELAY = 300" in html
    assert "static LOAD_TIMEOUT = 15000" in html
    assert "_gate('jobsSkeleton')" in html


def test_skeleton_only_renders_once_the_gate_has_opened(html):
    """The gated flag, ANDed with the machine state and with having no content —
    a refetch over data already on screen must keep the data."""
    assert "jobsSkeleton:s.jobsSkeleton&&s.jobsState==='loading'&&s.jobs.length===0" in html


def test_feed_has_a_real_state_machine(html):
    """loading -> ready | error, not a bare boolean."""
    assert "jobsState:'loading'" in html
    assert "jobsReady:s.jobsState==='ready'" in html
    assert "jobsFailed:s.jobsState==='error'" in html
    # the old boolean is gone
    assert "jobs:[], loading:true" not in html


def test_load_failure_produces_an_error_state_with_a_retry(html):
    """Never a bare toast: state what failed and offer the retry inline."""
    assert "_jobsFailed(" in html
    assert "retryJobs:()=>this.loadJobs()" in html
    assert 'onclick="{{ retryJobs }}"' in html
    assert 'role="alert"' in html


def test_timeout_swaps_the_skeleton_for_an_error(html):
    assert "The job feed did not answer within 15 seconds." in html


# --------------------------------------------------------------------------- #
# Skeletons trace the real content (§3.1-3.5)
# --------------------------------------------------------------------------- #

def test_skeleton_utility_is_theme_agnostic_and_sweeps_the_background(html):
    """color-mix against currentColor works in both themes with one definition,
    and the shimmer animates background-position, never width."""
    assert "--skeleton-base:color-mix(in oklch, currentColor" in html
    assert "@keyframes jf-skeleton-sweep{to{background-position:-150% 0}}" in html
    assert "animation:jf-skeleton-sweep var(--dur-ambient) linear infinite" in html


def test_skeleton_card_traces_every_row_of_the_real_card(html):
    """Same seven rows as decorate()'s card, with a short final text line."""
    assert "skeletonJobCard(i)" in html
    for marker in ("row 1 — source badge", "row 5 — description", "row 7 — the five icon actions"):
        assert marker in html
    # last description line is shorter than the rest (§3.2)
    assert "b('d4','62%','11px'" in html


def test_skeleton_containers_are_marked_busy_and_hidden_from_readers(html):
    assert 'aria-busy="true" aria-label="Loading jobs"' in html
    assert 'aria-busy="true" aria-label="Loading saved jobs"' in html
    assert "'aria-hidden':'true'" in html


def test_every_feed_gets_the_ladder(html):
    """New Jobs, Saved, and the Tracker all render skeletons, not a false empty."""
    assert html.count('<sc-if value="{{ jobsSkeleton }}"') >= 3
    assert "skeletonTrackerCards" in html
    assert "skeletonPanelFields" in html


# --------------------------------------------------------------------------- #
# Empty states are gated on the machine, never inferred from a zero count
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "expr",
    [
        "gridEmpty:gridJobs.length===0&&s.jobsState==='ready'",
        "savedEmpty:savedJobs.length===0&&s.jobsState==='ready'",
        "empty:jobs.length===0&&s.jobsState==='ready'",
    ],
)
def test_empty_states_require_a_ready_feed(html, expr):
    assert expr in html


def test_empty_state_offers_the_next_action(html):
    """An invitation to act, and a different one when a search is what emptied it."""
    assert "No job in the feed matches that search." in html
    assert 'onclick="{{ clearNewSearch }}"' in html
    assert 'onclick="{{ openFind }}"' in html


# --------------------------------------------------------------------------- #
# Panels have the same ladder
# --------------------------------------------------------------------------- #

def test_panels_wait_for_their_fetch_before_rendering_fields(html):
    assert "docsTabCandidate:s.docsTab==='candidate'&&!s.pfLoading&&!s.pfError" in html
    assert "optTabLlm:s.optionsTab==='llm'&&!s.optLoading" in html
    assert "guidanceSkeleton:s.guidanceSkeleton&&s.guidanceLoading" in html
    assert 'onclick="{{ retryProfile }}"' in html


def test_slow_buttons_have_a_fixed_width_loading_variant(html):
    """The spinner replaces the icon; min-width keeps the button from resizing."""
    assert "min-width:172px" in html          # Analyze matches
    assert "min-width:164px" in html          # Test connection
    assert html.count('class="jf-spin"') >= 3
    assert "analyzeBusyAttr:s.analyzing?'true':'false'" in html


# --------------------------------------------------------------------------- #
# Motion tokens (§2)
# --------------------------------------------------------------------------- #

REQUIRED_MOTION_TOKENS = [
    "--dur-instant", "--dur-fast", "--dur-base", "--dur-slow", "--dur-ambient",
    "--ease-out", "--ease-in", "--ease-soft",
    "--lift-sm", "--lift-md", "--lift-lg", "--stagger-step", "--focus",
]


@pytest.mark.parametrize("token", REQUIRED_MOTION_TOKENS)
def test_motion_token_defined(html, token):
    assert re.search(r":root\{[^}]*" + re.escape(token) + r":", html, re.S)


def test_stagger_is_capped(html):
    """Cumulative stagger stays under 500ms however long the list is."""
    assert "calc(min(var(--i,0),8) * var(--stagger-step))" in html


def test_exits_are_faster_than_entrances(html):
    """closeWithExit runs the exit keyframes for --dur-fast (140ms) before unmount."""
    assert "@keyframes jf-fade-out" in html
    assert "@keyframes jf-slide-out" in html
    assert "@keyframes jf-pop-out" in html
    assert "closeWithExit(key, commit)" in html


# --------------------------------------------------------------------------- #
# Accessibility floor (§9)
# --------------------------------------------------------------------------- #

def test_reduced_motion_is_honoured(html):
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "animation-iteration-count:1 !important" in html
    # the shimmer must stop rather than run at 0.01ms
    assert ".jf-skel{animation:none !important" in html


def test_focus_ring_outranks_the_exports_inline_outline_none(html):
    assert ":focus-visible{" in html
    assert "outline:2px solid var(--focus) !important" in html


def test_skip_link_is_the_first_focusable_node(html):
    body = html.split("<x-dc>", 1)[1]
    assert body.index('class="jf-skip"') < body.index("<button")
    assert 'id="jf-main"' in html


def test_async_regions_announce_politely(html):
    assert 'aria-live="polite" role="status"' in html
    assert html.count('aria-live="polite"') >= 4


def test_touch_targets_reach_44px_on_coarse_pointers(html):
    assert "@media (pointer:coarse)" in html
    assert "min-height:44px" in html


def test_every_overlay_is_findable_and_labelled_as_a_dialog(html):
    """Esc, the focus trap, and focus restore all key off [data-overlay]."""
    for name in ("detail", "profile", "options", "apply", "find", "analyze", "match"):
        assert f'data-overlay="{name}"' in html
    assert html.count('role="dialog" aria-modal="true"') == 7


def test_escape_closes_the_topmost_overlay(html):
    assert "if(e.key==='Escape')" in html
    assert "this.closeOverlay(root.getAttribute('data-overlay'))" in html


def test_tab_is_trapped_and_focus_is_restored(html):
    assert "if(e.key!=='Tab') return;" in html
    assert "this._lastFocus=document.activeElement" in html
    assert "document.body.style.overflow='hidden'" in html


# --------------------------------------------------------------------------- #
# Responsiveness (§8a)
# --------------------------------------------------------------------------- #

def test_no_grid_track_can_overflow_a_320px_viewport(html):
    assert "minmax(min(330px,100%),1fr)" in html
    assert "minmax(330px,1fr)" not in html


def test_full_height_sections_use_dvh(html):
    assert "dvh" in html
    assert re.search(r"(?<![\w-])\d+vh\b", html) is None


def test_cards_query_their_container_not_the_viewport(html):
    assert "container-type:inline-size" in html
    assert "@container (max-width: 320px)" in html
    assert "[data-cardactions]{flex-direction:column}" in html


def test_type_and_gutters_are_fluid(html):
    assert "--step-h1:clamp(" in html
    assert "--gutter:clamp(" in html
    assert "font:600 var(--step-h1)/1.1 var(--font-head)" in html


def test_reading_text_holds_a_14px_floor_on_phones(html):
    assert "[data-carddesc]{font-size:14px !important" in html


def test_offscreen_cards_are_cheap_to_skip(html):
    assert "content-visibility:auto;contain-intrinsic-size:auto 420px" in html


# --------------------------------------------------------------------------- #
# The runtime patch (§5)
# --------------------------------------------------------------------------- #

def test_generated_hover_rules_are_gated_behind_a_real_pointer():
    """Without this, tapping a card on a phone sticks its hover state."""
    js = RUNTIME_JS.read_text(encoding="utf-8")
    assert '"@media (hover:hover) and (pointer:fine){"' in js
    assert 'if (pseudo === "hover")' in js
