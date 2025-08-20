# auto-local

Provision local WordPress sites with Nginx, MariaDB, and `/etc/hosts`.

## Usage

`./autolocal.py --create DOMAIN`
`./autolocal.py --remove DOMAIN`

## Structure

- `autolocal.py` — entrypoint, config, CLI
- `config.py` — shared constants
- `modules/` — implementation modules
  - `modules/nginx.py` — vhost + site dir
  - `modules/wordpress.py` — wp-cli + theme/plugin config
  - `modules/dns.py` — `/etc/hosts` patch
  - `modules/utils.py` — helpers
- `data/` — templates and lists
  - `nginx_server_block.txt`
  - `plugins.tsv`, `themes.tsv`
  - `wp_cli_commands.txt`
- `docs/` — logs and checklist
  - `AGENTSLOG.md`, `CHECKLIST.md`, `smol-stuf-to-fix.md`


## Elementor Seeding Flow

- Purpose: seeds a starter Elementor page from a JSON template so new
  sites are Elementor-ready out of the box.

- Config variables (in `config.py`):
  - `ELEMENTOR_SEED`: 1 enables seeding, set to 0 to disable.
  - `ELEMENTOR_TPL_PATH`: path to template JSON to import.
  - `ELEMENTOR_PAGE_TITLE`: title for the created Elementor page.

- How to enable/disable: set `ELEMENTOR_SEED` to `1` or `0`.

- Expected output: Elementor plugin is active, the template is imported
  into the Elementor library, a new page is created with the template
  applied, and permalinks are flushed.

## Logging

- Console: terse PASS/FAIL lines only, each with a run-id.
- Files: detailed logs at `log/autolocal-<run-id>.log` (rotating).
- Correlate: use the run-id shown in console to open the matching log file.

Coding rules: see AGENTS.md
