# TODO: Practical Refactor Plan (Auto-Local WP)

Goal: clean, reliable, vim-editable code; no cleverness. Keep scope tight and follow KISS/DRY/YAGNI/SRP.

## Principles & Invariants
- One write path: `wordpress/installer.setup_wordpress()` orchestrates provisioning.
- SRP: parsing-only functions parse; file ops only write; CLI wrappers only run.
- Idempotent steps with explicit postconditions; fail fast on error.
- WP-CLI: prefer `--format=json` for programmatic reads; sanitize input; tolerate noise; never switch to CSV.
- Logs: log facts (IDs, counts, paths), not vibes. Use `status_pass/status_fail` for CLI, `log` for file logs.

## Phase 1 — WP-CLI consistency and JSON-only
- [x] Add brief invariants note to `modules/wordpress/cli.py` header (document default flags for read-ish commands).
- [x] Ensure `wp_cmd_capture()` returns JSON stringified from `wp_cmd_json()` result (already true; verify call sites).
- [x] Replace CSV usage in menus:
  - [x] Update `modules/wordpress/site.py:_menu_exists` to use `wp menu list --fields=name --format=json` and check names.
- [x] Grep repo for any non-JSON `--format=csv` or ad hoc parsing in WP calls; convert to JSON (+ robust parsing).

## Phase 2 — Elementor seeding hardening
- [ ] Use file-based meta updates to avoid arg length limits:
  - [ ] In `modules/wordpress/elementor_templates.py`, replace direct `_elementor_data` `wp post meta update` with `_update_post_meta_from_file()`.
- [ ] Deterministic media/id remap:
  - [ ] Deduplicate helpers (`_normalize_url`, `_unsize`), keep single definitions.
  - [ ] Remove `[JUIFU ...]` prints; use `logging`/`log`; keep walker small and explicit.
  - [ ] Ensure `json_update_ids_from_urls()` returns stable JSON (no unnecessary re-ordering beyond normal dumps).
- [ ] Flush Elementor CSS once after seeding; treat failure as error.
- [ ] Centralize vault path and template defaults in `config.py` (confirm current values; no hardcoding in modules).

## Phase 3 — Verification (contracts)
- [ ] Add `verify_provision(domain)` (likely in `installer.py` or `site.py`):
  - [ ] Assert pages `home`, `services`, `contact` exist (status=publish).
  - [ ] If seeding enabled, assert `_elementor_data` meta present and non-empty for each page.
  - [ ] Assert `elementor flush_css` completed.
  - [ ] Log summary: page IDs, Elementor meta sizes, CSS flush status.
- [ ] Call `verify_provision(domain)` at end of `setup_wordpress()`; fail if verification fails.

## Phase 4 — Cleanup & readability
- [ ] Remove dead/duplicate imports and helpers in `modules/wordpress/elementor_templates.py`.
- [ ] Add one-sentence docstrings for exported functions (SRP, inputs/outputs) across `site.py`, `elementor_templates.py`, `plugins_themes.py`, `installer.py`.
- [ ] Ensure early returns, one condition per line; reduce nesting.
- [ ] Keep line lengths ~≤80 cols where practical.

## Phase 5 — Minimal dev-only checks
- [ ] Add small smoke checks under `tests/` (dev-run only, not CI):
  - [ ] `wp_cmd_json` returns correct types for a known local site path.
  - [ ] `verify_provision(domain)` passes for a seeded test site (guard via env var).

## Non-goals (intentionally excluded)
- Rollbacks and transactional changes.
- Marketplace/theme/plugin feature expansion.
- New CLI UX or shiny abstractions.

## Files to touch
- `modules/wordpress/cli.py` (doc note)
- `modules/wordpress/site.py` (JSON menus, verify helpers, docs)
- `modules/wordpress/installer.py` (call `verify_provision`, docs)
- `modules/wordpress/elementor_templates.py` (seeding cleanup, file-based meta, dedupe helpers)
- `config.py` (confirm vault/template toggles/paths)

## Status Notes
- Start with Phase 1 + Phase 2 for the highest reliability gains with minimal diff.
- Keep changes surgical; mirror existing patterns and naming.

## Q&A Decisions (Phase‑1 principles)
- WP‑CLI defaults: route all calls through the `wp_json` silencing wrapper; enforce
  `--format=json` and `--quiet`; keep noise stripping on.
- Return types: all `wp_cmd*` wrappers return JSON strings; return empty JSON
  (`[]`/`{}`) when WP outputs nothing; never `None`.
- Menu matching: use normal exact name matching as returned by WP; no custom
  normalization.
- Error handling: log pass/fail for every WP‑CLI call; continue on trivial
  failures; halt when failure would leave unknown state (use judgment; no
  criticality tagging system).
- Logging: console prints stay minimal “progress/ok”; file logs remain extremely
  explicit with factual details; keep current `.log` format.
- Refactor posture: minimal diffs, remove non‑essential code; use the wrapper
  consistently but avoid big rewires; KISS/DRY/YAGNI.
- Paradigm: prefer plain functions; avoid OOP.
