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


## Elementor

- Vault-only seeding: Elementor content is provisioned from a preset in
  the vault when `--preset=KEY-V` is supplied during `--create`.
- Without a preset: Elementor seeding is skipped. No local template
  files are used.

## Logging

- Console: terse PASS/FAIL lines only, each with a run-id.
- Files: detailed logs at `log/autolocal-<run-id>.log` (rotating).
- Correlate: use the run-id shown in console to open the matching log file.

Coding rules: see AGENTS.md
