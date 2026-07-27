"""Guard the logo-derived theme contract in the frontend shell.

The whole UI recolors through the CSS custom properties defined in
``Component.THEMES`` inside ``utils/frontend/templates/index.html``. These
tests pin the parts a future edit could silently break:

  * both themes (``arctic`` light, ``midnight`` dark) exist and the retired
    ``editorial``/``neon`` themes are gone
  * each theme block defines every token the template consumes
  * the brand colors sampled from ``images/magnify.svg`` are present
  * the header theme toggle is wired (switch role + persistence key)
"""

import re

import pytest

from app import application

# Every var(--*) name the template consumes from a theme block.
REQUIRED_TOKENS = [
    "--bg", "--surface", "--surface2", "--card", "--text", "--muted",
    "--border", "--border2", "--bw", "--accent", "--accent-ink",
    "--accent-text", "--accent2", "--danger", "--c-applied", "--c-interview",
    "--c-offer", "--c-offer-text", "--c-reject", "--c-archive",
    "--radius", "--r-sm", "--font-head", "--font-body", "--font-mono",
    "--shadow",
]

# The four color families of the penguin logo (images/magnify.svg).
BRAND_ORANGE = "#F4A226"
BRAND_NAVY = "#132433"
BRAND_WHITE = "#F7F6F5"


@pytest.fixture
def html():
    application.config["TESTING"] = True
    with application.test_client() as c:
        return c.get("/").get_data(as_text=True)


def _theme_block(html, name):
    """Return the source of one theme's token object from Component.THEMES."""
    match = re.search(name + r":\s*\{(.*?)\}", html, re.S)
    assert match, f"theme {name!r} not found in index.html"
    return match.group(1)


def test_only_logo_themes_exist(html):
    assert "arctic" in html and "midnight" in html
    assert "editorial" not in html
    assert "neon" not in html


@pytest.mark.parametrize("name", ["arctic", "midnight"])
def test_theme_defines_all_tokens(html, name):
    block = _theme_block(html, name)
    missing = [t for t in REQUIRED_TOKENS if f"'{t}'" not in block]
    assert not missing, f"{name} is missing tokens: {missing}"


def test_brand_colors_present(html):
    arctic = _theme_block(html, "arctic")
    midnight = _theme_block(html, "midnight")
    for block in (arctic, midnight):
        assert BRAND_ORANGE in block, "accent must stay the beak orange"
    assert BRAND_NAVY in arctic, "arctic text must be the logo navy"
    assert BRAND_NAVY in midnight, "midnight surface must be the logo navy"
    assert BRAND_WHITE in midnight, "midnight text must be the belly off-white"


def test_header_and_sidebar_always_midnight(html):
    """Header and sidebar re-scope the theme vars to the logo navy in both themes."""
    header = re.search(r"<header\b[^>]*>", html).group(0)
    sidebar = re.search(r"sidebarStyle:'[^']*'", html).group(0)
    for chrome, name in ((header, "header"), (sidebar, "sidebar")):
        for override in ("--surface:#132433", "--text:#F7F6F5", "--border:#24394E"):
            assert override in chrome, f"{name} must pin {override}"
        assert "color:var(--text)" in chrome, f"{name} must re-resolve inherited text color"


def test_theme_toggle_wired(html):
    assert 'aria-label="Toggle theme"' in html
    assert 'role="switch"' in html
    assert "magnify.theme" in html, "theme choice must persist to localStorage"
