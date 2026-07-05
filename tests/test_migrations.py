"""Migrations must apply on a clean DB and fully roll back.

Runs the real Alembic CLI in a subprocess (fresh process = fresh settings cache
and its own event loop for the async env) against a throwaway SQLite file.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _alembic(args, db_url):
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    env["BOT_TOKEN"] = "test:token"
    env["ADMIN_IDS"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_upgrade_then_downgrade(tmp_path):
    db_file = tmp_path / "mig.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    up = _alembic(["upgrade", "head"], db_url)
    assert up.returncode == 0, up.stderr
    assert db_file.exists()

    import sqlite3

    con = sqlite3.connect(db_file)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    con.close()
    assert {"users", "applications", "events", "teams", "logs"} <= tables

    down = _alembic(["downgrade", "base"], db_url)
    assert down.returncode == 0, down.stderr

    con = sqlite3.connect(db_file)
    tables_after = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    con.close()
    # every app table dropped by downgrade (alembic_version may remain)
    assert not ({"users", "applications", "events", "teams", "logs"} & tables_after)
