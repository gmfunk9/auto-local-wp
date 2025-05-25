# dns_local.py
#!/usr/bin/env python3
import sys
from pathlib import Path
from autolocal import HOSTS_FILE, LOCALHOST_IP

def read_hosts_file():
    hosts_path = Path(HOSTS_FILE)
    if not hosts_path.exists():
        return []
    with open(hosts_path, 'r') as f:
        return f.readlines()

def write_hosts_file(lines):
    try:
        with open(HOSTS_FILE, 'w') as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"FAIL: Could not write hosts file: {e}", file=sys.stderr)
        return False

def add_domain_to_hosts(domain):
    lines = read_hosts_file()
    entry = f"{LOCALHOST_IP} {domain}\n"
    domain_exists = False
    updated_lines = []
    for line in lines:
        if line.strip() and domain in line:
            if line.startswith(LOCALHOST_IP):
                domain_exists = True
                updated_lines.append(entry)
            else:
                continue
        else:
            updated_lines.append(line)
    if not domain_exists:
        updated_lines.append(entry)
    if write_hosts_file(updated_lines):
        print(f"PASS: Added {domain} to hosts file")
        return True
    return False

def remove_domain_from_hosts(domain):
    lines = read_hosts_file()
    updated_lines = []
    found = False
    for line in lines:
        if line.strip() and domain in line and line.startswith(LOCALHOST_IP):
            found = True
            continue
        updated_lines.append(line)
    if write_hosts_file(updated_lines):
        if found:
            print(f"PASS: Removed {domain} from hosts file")
        else:
            print(f"PASS: Domain {domain} not found in hosts file")
        return True
    return False

def main():
    domain = sys.argv[1]
    remove = "--remove" in sys.argv
    if remove:
        ok = remove_domain_from_hosts(domain)
    else:
        ok = add_domain_to_hosts(domain)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
