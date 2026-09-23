"""Pin the favorite-company star and the reworked job detail header into the served page.

The frontend is one design export with no build step, so the durable guard is to assert on the
HTML the app serves. These tests encode:

  * the detail header is two rows — [star] company … [block][hide][save][copy], then the title —
    with the initials "logo" placeholder and the pulsing dot gone;
  * the star is a real, labelled toggle button styled like its four siblings, and says its state
    with a filled/outlined icon as well as color;
  * starring writes through ``/api/profile/favorite-company`` only, favorites load at mount,
    and blocking a company drops its star;
  * New Jobs, Saved, and Tracker cards all read the favorite-aware border.

The browser pane does not composite in this environment; the API side is covered by
``tests/profile/test_profile_favorite_api.py`` and the layout was checked in headless Chromium.
"""

import re

import pytest

from app import application


@pytest.fixture
def html():
    application.config["TESTING"] = True
    with application.test_client() as c:
        return c.get("/").get_data(as_text=True)


def _detail_header(html):
    start = html.index('data-overlay="detail"')
    end = html.index("{{ selectedJob.compensation }}", start)
    return html[start:end]


def test_header_drops_logo_placeholder_and_pulse(html):
    head = _detail_header(html)
    assert "avatarLg" not in head and "initials" not in head
    assert "jf-pulse" not in head
    assert "avatarLg" not in html


def test_header_row_order_star_company_actions_then_title(html):
    head = _detail_header(html)
    order = [
        "{{ selectedJob.onFavorite }}",
        "{{ selectedJob.company }}",
        "{{ selectedJob.onBlock }}",
        "{{ selectedJob.onIgnore }}",
        "{{ selectedJob.onSave }}",
        "{{ selectedJob.onCopy }}",
        "{{ selectedJob.title }}",
    ]
    positions = [head.index(tok) for tok in order]
    assert positions == sorted(positions), "detail header controls are out of order"
    # The title sits on its own row, after the action group closes.
    assert re.search(r"</div>\s*</div>\s*<h2[^>]*>\{\{ selectedJob\.title \}\}</h2>", head)


def test_star_is_an_accessible_toggle_like_its_siblings(html):
    head = _detail_header(html)
    star = re.search(r"<button onclick=\"\{\{ selectedJob\.onFavorite \}\}\"[^>]*>", head).group(0)
    assert 'aria-label="{{ selectedJob.favTitle }}"' in star
    assert 'aria-pressed="{{ selectedJob.favPressed }}"' in star
    assert 'style="{{ selectedJob.favBtn }}"' in star
    # Every header icon button carries an accessible name now (Hide had none before).
    for tok in ("onBlock", "onIgnore", "onSave", "onCopy"):
        btn = re.search(r"<button onclick=\"\{\{ selectedJob\.%s \}\}\"[^>]*>" % tok, head).group(0)
        assert "aria-label=" in btn, f"{tok} button has no aria-label"
    # Same 34px geometry as the save button, and state shown by fill, not color alone.
    assert "favBtn:'display:flex;align-items:center;justify-content:center;width:34px;height:34px" in html
    assert "favIcon:'fill:'+(fav?'currentColor':'none')" in html


def test_favorites_load_at_mount_and_write_through_the_toggle_endpoint(html):
    mount = html[html.index("componentDidMount(){"):]
    assert "this.loadFavorites();" in mount[:200]
    assert "fetch('/api/profile/favorite-company'" in html
    assert "toggleFavoriteCompany(company){" in html
    # The Profile panel save never sends favorites (the toggle endpoint is the only writer).
    save = html[html.index("  saveProfile(){"):]
    save = save[: save.index("fetch(")]
    assert "favorite_companies" not in save


def test_blocking_a_company_drops_its_star(html):
    block = html[html.index("  blockCompany(company){"):]
    block = block[: block.index("\n  }\n")]
    assert "favoriteCompanies:st.favoriteCompanies.filter(" in block
    assert "d.favorite_companies" in block


def test_every_card_surface_uses_the_favorite_border(html):
    # New Jobs + Saved share cardStyle; the Tracker card has its own favorite-aware style.
    assert html.count('style="{{ job.cardStyle }}"') == 2
    assert 'style="{{ job.trackerCardStyle }}"' in html
    assert "const edge=j.ignore?'var(--danger)':(fav?'var(--accent)':'var(--border)');" in html
    assert "trackerCardStyle:'cursor:grab;background:var(--card);border:var(--bw) solid '+(fav?'var(--accent)'" in html
