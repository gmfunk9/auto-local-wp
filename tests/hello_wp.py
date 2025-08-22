#!/usr/bin/env python3
"""Minimal smoke test: hello-WordPress via WP-CLI.

- Targets site "autolocalwp-testing-01.local" by default
- Read-only probes: home, siteurl, plugin list, theme list
- Emits a single compact JSON line then a PASS/FAIL line
- Set env AUTOLOCAL_TEST_DOMAIN and AUTOLOCAL_RID to override
"""

from __future__ import annotations

import json
import os

from modules.utils import init_logging, status_pass, status_fail
from modules.wordpress.cli import wp_cmd_json


DEFAULT_DOMAIN = "autolocalwp-testing-01.local"


def main() -> int:
    # Default a stable run-id unless caller sets AUTOLOCAL_RID
    os.environ.setdefault("AUTOLOCAL_RID", "hello")
    init_logging(None)

    domain = os.environ.get("AUTOLOCAL_TEST_DOMAIN", DEFAULT_DOMAIN)

    ok, home = wp_cmd_json(domain, "option get home")
    if not ok:
        status_fail(f"option get home failed for {domain}")
        return 1

    ok, siteurl = wp_cmd_json(domain, "option get siteurl")
    if not ok:
        status_fail(f"option get siteurl failed for {domain}")
        return 1

    ok, plugins = wp_cmd_json(domain, "plugin list")
    if not ok:
        status_fail(f"plugin list failed for {domain}")
        return 1

    ok, themes = wp_cmd_json(domain, "theme list")
    if not ok:
        status_fail(f"theme list failed for {domain}")
        return 1

    plugins_count = 0
    if isinstance(plugins, list):
        plugins_count = len(plugins)

    themes_count = 0
    if isinstance(themes, list):
        themes_count = len(themes)

    result = {
        "domain": domain,
        "home": home,
        "siteurl": siteurl,
        "plugins_count": plugins_count,
        "themes_count": themes_count,
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    status_pass(f"hello-wordpress ok for {domain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
