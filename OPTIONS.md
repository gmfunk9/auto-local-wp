**Elementor Import: YAGNI-Focused Options**
- **Context:** Current vault preset flow imports only the first image found in `_elementor_data`, rewrites a single `id`, and already flushes Elementor CSS. Non-vault flow seeds from a staged JSON template and does not flush CSS. Duplicate media imports are acceptable.

**Objective**
- Keep the existing flow. Add the smallest reliable tweaks to import all images and keep pages usable. No JSON saves, no traversal engine, no dedupe cache.

**Option 1 — Minimal fix (recommended)**
- **Import all images:**
  - Replace the single-URL extractor with a simple multi-match regex over the blob: `re.findall(r"http[^\"]+uploads[^\"]+\.(jpg|jpeg|png|webp)", blob, re.I)`, normalize `\\/` → `/`, dedupe with `set()`.
  - For each URL, reuse the existing `_import_media_from_vault(domain, clean_url)` and collect `{url -> new_id}`. Ignore failures per URL and continue.
- **Rewrite host and nearby ids (best-effort):**
  - Replace the vault host with the target `domain` in the entire blob.
  - For each imported URL, update any adjacent `"id": <num>` paired with that URL using two conservative regex passes within a short window (e.g., 0–200 chars): one where `url` appears before `id`, and one where `id` appears before `url`. If no match, leave as-is; the URL alone is sufficient for editor fallback.
- **Flush CSS everywhere:** After setting `_elementor_data` on pages, run `wp elementor flush_css` in both preset and non-preset flows.
- **Placeholder TODO (no-op):** Leave a stub call point to optionally apply simple string replacements (phone/email/etc.) before writing meta; disabled by default.

**Option 2 — Even smaller change**
- **Import all images; skip id rewrites:**
  - Same multi-URL import as Option 1.
  - Only swap the host in URLs and set the blob; do not attempt `id` updates. Pages remain functional since URLs resolve; any mismatched `id` can be fixed later in the editor if needed.
  - Flush CSS in both flows.

**Trade-offs**
- Option 1 slightly improves fidelity by updating nearby ids without deep parsing; adds minimal regex only.
- Option 2 is the smallest change surface and relies on Elementor/editor tolerance to URL-only correctness.

**Touch Points (later implementation)**
- `modules/wordpress/elementor_templates.py`
  - Replace `_first_upload_url` with `_find_upload_urls` (multi-URL regex) in the preset flow.
  - Apply the same multi-URL import + host swap in the non-vault flow around the template meta copy.
  - Add `wp elementor flush_css` to the non-vault flow after seeding.
  - Optional: placeholder string-replace hook call point (no-op by default).
