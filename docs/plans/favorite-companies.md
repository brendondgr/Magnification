# Favorite Companies + Detail Panel Header — Plan

## 1. Introduction

The user wants to bookmark whole **companies**, not just individual jobs, so that any job from a
company they care about stands out wherever it appears. Today the only company-level control is
**Block** (`blockCompany` → `POST /api/profile/block-company`, persisted on `Profile.blocked_companies`);
there is no positive counterpart. This plan adds one: a **star** in the job detail panel that toggles
the job's company in a new `Profile.favorite_companies` list, and an accent-colored outline on every
New Jobs, Saved, and Tracker card whose company is in that list.

The same change tidies the detail panel header, which the user finds messy: the 52px initials
"logo" placeholder and the pulsing yellow dot are removed; the first row becomes
**[star] Company name ……… [Block] [Hide] [Save] [Copy]**, with the star styled exactly like the
other four 34px icon buttons; the job title moves to its own row underneath. Favorites mirror the
existing blocklist end-to-end (JSON column on the active profile, idempotent migration, a dedicated
toggle endpoint, an optimistic client update), so there is no new storage pattern to learn.

This is the first of the two "company depth" layers the user mentioned; the second is not yet
specified and is out of scope here.

## 2. Gaps & Unanswered Questions

- **Where favorites live.** *Assumption:* on the active `Profile`, next to `blocked_companies`, matched
  case-insensitively on the trimmed company name — the same identity rule Block already uses.
- **Blocking a favorite.** The two are contradictory. *Assumption:* blocking a company also removes it
  from favorites (server-side in `block-company`, mirrored optimistically in the client).
- **Does favoriting exempt jobs from auto-hide?** Not requested. *Assumption:* no — favorites are
  purely visual in this layer. Saved jobs remain the only auto-hide exemption.
- **Outline precedence on an ignored card.** *Assumption:* the red "ignored" border wins, since it
  communicates a state the user must act on (only visible under Show Ignored).
- **Outline color.** *Assumption:* `--accent` (the logo amber, i.e. "star gold"), distinct from Saved's
  `--accent2` and Ignored's `--danger`. It exists on both themes, so no new token is needed.
- **Profile rebuild from a résumé.** The builder never emits `favorite_companies`, and
  `upsert_active_profile` only writes keys it is given, so a rebuild or a Profile-panel save cannot
  wipe favorites. The general `POST /api/profile` whitelist deliberately does **not** accept the field;
  the toggle endpoint is the only writer.
- **A management UI (list/unfavorite from the Profile panel).** Not requested. *Assumption:* un-starring
  from any of that company's jobs is enough for now; noted in `docs/checklist.md`.
- **The second "layer" of company tracking.** *Human intervention is needed to answer this question* —
  the user said they will describe it after this one lands.

## 3. Hierarchical Step-by-Step Instructions

Work happens on branch `feature/favorite-companies` in the worktree
`.claude/worktrees/favorite-companies` (other agents share the main checkout). Commit per step;
**do not push** until the user says so. No multi-agent workflow is used: the change touches a
handful of known locations and is faster to do directly than to delegate.

#### Step 1: Persist favorite companies on the profile

- **Locations**:
  - `utils/backend/database/models.py` — `Profile.favorite_companies` JSON column + docstring line.
  - `utils/backend/database/migrate_profile_favorites.py` (new) — idempotent `ALTER TABLE profiles ADD
    COLUMN favorite_companies TEXT`, modeled on `migrate_profile_blocklists.py`.
  - `utils/backend/database/init_db.py` — `_run_migrations()` imports and calls it.
  - `utils/backend/database/operations.py` — add to `_PROFILE_FIELDS` and `_profile_to_dict`.
  - `utils/backend/routes/profile_routes.py` `get_profile()` — the no-profile skeleton gains
    `favorite_companies: []`. (Not added to `EMPTY_PROFILE`: that dict seeds résumé-build *drafts*,
    and a draft carrying `[]` must never look like "clear my favorites".)
  - `docs/database.md`, `docs/structure.md` (only if the migration list is enumerated there).
- **Rationale**: Every later step reads or writes this list; the migration is required because the
  user's existing database predates the column and `create_all` never alters existing tables.
- **Tests**: `tests/database/test_profile_favorites.py` — migration adds the column to a
  temp SQLite file and is a no-op on the second run; a profile round-trips the list.
- *Action: Undergo the verification/tests/validation process for this phase (`uv run pytest
  tests/database tests/profile`, `import app`). Once validated, commit stating: Favorite Companies
  (1/4) Complete: Added a favorite_companies list to the profile with an idempotent migration.*

#### Step 2: Toggle endpoint, and blocking clears a favorite

- **Locations**:
  - `utils/backend/routes/profile_routes.py` — new `POST /api/profile/favorite-company`, body
    `{company, favorite}` (`favorite` optional → toggle). De-dupes case-insensitively, keeps the
    first-seen spelling, returns `{success, favorite, favorite_companies}`; 400 on a blank company.
    `block_company()` also drops the company from `favorite_companies` and returns the new list.
  - `docs/routes.md`, `docs/api-contract.md` — the new endpoint and the extended block response.
- **Rationale**: A dedicated endpoint keeps the one-click star atomic and independent from the
  Profile-panel save (which must not be able to clobber favorites with a stale copy).
- **Tests**: `tests/profile/test_profile_favorite_api.py` on an in-memory engine (the
  `init_db.SessionLocal` patch used by `test_profile_block_api.py`): add, idempotent add with different
  casing, explicit remove, toggle, blank → 400, block removes the favorite, `POST /api/profile` ignores
  a `favorite_companies` key.
- *Action: Undergo the verification/tests/validation process for this phase. Once validated, commit
  stating: Favorite Companies (2/4) Complete: Added the favorite-company toggle endpoint and made
  blocking a company clear its favorite.*

#### Step 3: Rework the detail panel header, add the star, and outline favorite cards

- **Locations** (`utils/frontend/templates/index.html`):
  - `DETAIL PANEL` markup — delete the `avatarLg`/`initials` block and the `jf-pulse` dot; row 1 is a
    flex row of the star button, the company name (`flex:1;min-width:0`, ellipsis on overflow, full
    name in `title`), then the Block / Hide / Save / Copy group; row 2 is the `<h2>` title spanning
    the full width. Give Hide an `aria-label`/`title` while there (it has none today).
  - `decorate(j)` — `isFavorite`, `favTitle`, `favBtn` (same 34px geometry as `saveBtn`, filled
    `--accent` star when on), `onFavorite`; drop the now-unused `avatarLg`.
  - New `isFavoriteCompany(name)` and `toggleFavoriteCompany(company)` beside `blockCompany`:
    optimistic update of `state.profile.favorite_companies`, toast, POST, reconcile from the
    response, revert + toast on failure. `blockCompany` also removes the name from the local list.
  - Favorites live in their own `state.favoriteCompanies` (loaded at mount by `loadFavorites()`, also
    refreshed by `loadProfile()`), not inside `state.profile`, because the profile is otherwise only
    loaded when the Profile panel opens and the outlines must show from first paint.
  - `decorate(j)` `cardStyle` border uses `--accent` when favorite and not ignored; new
    `trackerCardStyle` does the same for the Tracker card markup, which previously inlined its style.
    (Folded in from Step 4 — it is the same `decorate` edit.)
- **Rationale**: The header is where the user asked for the control, and removing the placeholder
  logo + ornamental dot frees the row the company name and star now share.
- *Action: Undergo the verification/tests/validation process for this phase (served-HTML wiring
  test; the browser pane does not composite here). Once validated, commit stating: Favorite
  Companies (3/4) Complete: Reworked the detail header into a star + company row above the title and outlined favorite companies' cards.*

#### Step 4: Wiring tests, accessibility pass, and docs

- **Locations**:
  - `index.html` `decorate(j)` — `cardStyle` border uses `--accent` when `isFavorite` (and not
    ignored); new `trackerCardStyle` does the same for the Tracker card markup, which currently
    inlines its style.
  - `tests/frontend/test_favorite_company_wiring.py` (new) — the served page wires the star
    (`onFavorite`, `favBtn`, `aria-pressed`), no longer renders `avatarLg`/`jf-pulse` in the detail
    header, calls `/api/profile/favorite-company`, and all three card surfaces consume the
    favorite-aware style.
  - Docs: `docs/component-map.md` (detail header layout, star, outline), `docs/design-system.md`
    (favorite outline = `--accent`, precedence under ignored), `docs/data-flow.md` (favorites flow),
    `docs/checklist.md` (shipped ledger row + open items: favorites management UI, second layer).
  - Run the `docs/skills/accessibility-mobile/SKILL.md` checklist: star is a real `<button>` with
    `aria-label` + `aria-pressed`, 34px target (matching its siblings), color is not the only signal
    (filled vs. outline star), header row wraps safely at 375px.
- **Rationale**: The outline is the payoff the user asked for — recognizing a favorite company the
  next time it appears — and docs must ship in the same change.
- *Action: Undergo the verification/tests/validation process for this phase (full `uv run pytest`
  minus the two known non-offline tests). Once validated, commit stating: Favorite Companies (4/4)
  Complete: Outlined favorite companies' cards everywhere and documented the feature.*

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Profile column | `favorite_companies` JSON list on the active profile | `utils/backend/database/models.py` |
| Migration | Idempotent column add for existing databases | `utils/backend/database/migrate_profile_favorites.py`, `init_db.py` |
| Toggle endpoint | `POST /api/profile/favorite-company`; block clears favorite | `utils/backend/routes/profile_routes.py` |
| Detail header | Star + company row above the title; logo placeholder and pulse dot removed | `utils/frontend/templates/index.html` (DETAIL PANEL, `decorate`, `toggleFavoriteCompany`) |
| Card outline | `--accent` border on New Jobs, Saved, and Tracker cards of favorite companies | `utils/frontend/templates/index.html` (`cardStyle`, `trackerCardStyle`) |
| Migration tests | Column added once, round-trip | `tests/database/test_profile_favorites.py` |
| API tests | Add/remove/toggle/de-dupe/400/block interaction | `tests/profile/test_profile_favorite_api.py` |
| Wiring tests | Served page wires star, header, and outlines | `tests/frontend/test_favorite_company_wiring.py` |
| Docs | Routes, contract, component map, design system, data flow, database, checklist | `docs/*.md` |
