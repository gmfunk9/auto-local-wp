"""MariaDB helpers used by WordPress installer."""

from __future__ import annotations

import logging
import subprocess
from typing import Tuple

from config import DB_PASS
from modules.utils import db_ident, log


def _mysql_try(sql: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["mariadb", "-e", sql], text=True, capture_output=True, check=True
        )
        return proc.returncode, (proc.stdout or ""), (proc.stderr or "")
    except subprocess.CalledProcessError as exc:
        return exc.returncode, (exc.stdout or ""), (exc.stderr or "")


def run_mysql(sql: str) -> bool:
    rc, out, err = _mysql_try(sql)
    msg = f"SQL: {sql}\nEXIT: {rc}\nSTDOUT: {(out or '').strip()}\nSTDERR: {(err or '').strip()}"
    if rc == 0:
        log(f"PASS: {msg}")
        return True
    logging.error(msg)
    return False


def _mysql_query(sql: str) -> tuple[int, str, str]:
    rc, out, err = _mysql_try(sql)
    return rc, (out or "").strip(), (err or "").strip()


def ensure_db_and_user(domain: str) -> bool:
    ident = db_ident(domain)
    dbname = ident
    dbuser = ident
    if not run_mysql(f"CREATE DATABASE IF NOT EXISTS `{dbname}`;"):
        return False
    if not run_mysql(
        "CREATE USER IF NOT EXISTS "
        f"'{dbuser}'@'localhost' IDENTIFIED BY '{DB_PASS}';"
    ):
        return False
    if not run_mysql(
        "GRANT ALL PRIVILEGES ON " f"`{dbname}`.* TO '{dbuser}'@'localhost';"
    ):
        return False
    if not run_mysql("FLUSH PRIVILEGES;"):
        return False
    return True


def _db_exists(dbname: str) -> bool:
    sql = (
        "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
        f"WHERE SCHEMA_NAME='{dbname}';"
    )
    rc, out, _ = _mysql_query(sql)
    if rc != 0:
        return False
    return bool(out)


def _db_user_exists(dbuser: str) -> bool:
    sql = (
        "SELECT 1 FROM mysql.user "
        f"WHERE user='{dbuser}' AND host='localhost';"
    )
    rc, out, _ = _mysql_query(sql)
    if rc != 0:
        return False
    return bool(out)

