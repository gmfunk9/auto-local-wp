# code-sample.md

## provision_elementor (AGENTS.md-compliant)

This sample implements `provision_elementor(domain)` as a small, SRP function that mirrors repo patterns (uses `wp_cmd` / `wp_cmd_capture`, uses `log()`, keeps errors visible). It appends one terse agent log line to `AGENT_ACTIVITY.log` after success.

```python
# modules/provision_elementor.py
from pathlib import Path
from datetime import datetime
from typing import Dict

# reuse project helpers to mirror existing patterns
from modules.wordpress import wp_cmd, wp_cmd_capture, log
try:
    # optional overrides in config.py (recommended)
    from config import ELEMENTOR_SEED, ELEMENTOR_TPL_PATH, ELEMENTOR_PAGE_TITLE
except Exception:
    ELEMENTOR_SEED = True
    ELEMENTOR_TPL_PATH = "data/elementor-page-templates/fp_fullpage-about-landscaping.json"
    ELEMENTOR_PAGE_TITLE = "Test Elementor Page"

AGENT_LOG = Path(__file__).resolve().parents[1] / "AGENT_ACTIVITY.log"


def _append_agent_log(line: str) -> None:
    """Append one terse, chronological log line. No code in the log."""
    ts = datetime.utcnow().isoformat() + "Z"
    with open(AGENT_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{ts} {line}\n")


def provision_elementor(domain: str) -> Dict[str, str]:
    """
    Idempotent. Returns {'tpl_id':..., 'page_id':...} on success.
    Steps:
      - ensure elementor plugin active
      - import template -> tpl_id
      - create or find page -> page_id
      - set _elementor_edit_mode and _elementor_version
      - copy _elementor_data from tpl -> page
      - flush rewrites (via wp_cmd)
    Errors raise RuntimeError so caller halts install (matches repo behavior).
    """
    if not ELEMENTOR_SEED:
        log("SKIP: elementor seeding disabled")
        return {}

    tpl_path = Path(ELEMENTOR_TPL_PATH)
    if not tpl_path.exists():
        raise FileNotFoundError(f"template not found: {tpl_path}")

    # 1) ensure plugin active (install+activate if needed)
    ok, _, _ = wp_cmd_capture(domain, ["plugin", "is-active", "elementor"])
    if not ok:
        log("INFO: elementor not active, installing")
        if not wp_cmd(domain, ["plugin", "install", "elementor", "--activate", "--quiet"]):
            raise RuntimeError("failed to install/activate elementor")

    # 2) import template (returns ID)
    ok, tpl_out, err = wp_cmd_capture(domain, ["elementor", "library", "import", str(tpl_path), "--returnType=ids", "--user=1"])
    if not ok or not tpl_out:
        raise RuntimeError(f"elementor import failed: {err}")
    tpl_id = tpl_out.splitlines()[-1].strip()
    log(f"PASS: imported tpl {tpl_id}")

    # 3) find or create page (idempotent)
    ok, existing, _ = wp_cmd_capture(domain, ["post", "list", "--post_type=page", f"--title={ELEMENTOR_PAGE_TITLE}", "--field=ID"])
    if ok and existing:
        page_id = existing.splitlines()[0].strip()
        log(f"INFO: found existing page {page_id}")
    else:
        ok, page_out, err = wp_cmd_capture(domain, ["post", "create", "--post_type=page", f"--post_title={ELEMENTOR_PAGE_TITLE}", "--post_status=publish", "--porcelain"])
        if not ok or not page_out:
            raise RuntimeError(f"failed to create page: {err}")
        page_id = page_out.strip()
        log(f"PASS: created page {page_id}")

    # 4) set edit mode
    if not wp_cmd(domain, ["post", "meta", "update", page_id, "_elementor_edit_mode", "builder"]):
        raise RuntimeError("failed to set _elementor_edit_mode")

    # 5) set elementor version (capture then write)
    ok, ver_out, _ = wp_cmd_capture(domain, ["plugin", "get", "elementor", "--field=version"])
    if not ok:
        raise RuntimeError("failed to read elementor version")
    version = ver_out.strip()
    if not wp_cmd(domain, ["post", "meta", "update", page_id, "_elementor_version", version]):
        raise RuntimeError("failed to set _elementor_version")

    # 6) copy elementor data from tpl -> page
    ok, tpl_data, err = wp_cmd_capture(domain, ["post", "meta", "get", tpl_id, "_elementor_data"])
    if not ok:
        raise RuntimeError(f"failed to read tpl _elementor_data: {err}")
    # pass JSON as single argv element to avoid shell splitting
    if not wp_cmd(domain, ["post", "meta", "update", page_id, "_elementor_data", tpl_data]):
        raise RuntimeError("failed to copy _elementor_data")

    # 7) flush rewrite rules
    if not wp_cmd(domain, ["rewrite", "flush", "--hard"]):
        raise RuntimeError("rewrite flush failed")

    # append one terse agent log line (chronological, factual)
    _append_agent_log(f"provision_elementor domain={domain} tpl={tpl_id} page={page_id}")
    log(f"PASS: elementor seeded tpl={tpl_id} page={page_id}")
    return {"tpl_id": tpl_id, "page_id": page_id}
```

## Simple explanation (1-2 lines)

This module is tiny, mirrors repo patterns (uses `wp_cmd` / `wp_cmd_capture` and `log()`), avoids shell hacks by passing args as lists, and appends a single terse agent log line to `AGENT_ACTIVITY.log`. Add `ELEMENTOR_*` vars to `config.py` later; keep changes minimal.

