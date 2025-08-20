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

Coding rules: see AGENTS.md

- must test wp command installing the wp_form json. method works but haven't tried in this setup. -- actually, the output "Success: Created post 245." when that command is used might be useful as WP forms creates shortcode: `[wpforms id="245"]	` we can only get that ID when we make that page? - no we could always just query for the post data at any time. --- yeah i tested, and this is not working. 1,) the commands are being run before the plugins are downloading. 2,) I added wpforms-lite to 'plugins.tsv' but the code did not install wpforms-lite. 


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
