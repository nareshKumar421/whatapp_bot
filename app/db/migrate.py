"""Simple file-based migration runner for SAP HANA.

Tracks applied migrations in a JIVO_WA_MIGRATIONS table.
SQL files in migrations/ are run in alphabetical order.
Use {schema} placeholder in SQL — replaced at runtime.
"""

import os

from app.db.connection import get_conn, release_conn, t
from app.logging_setup import log_hana

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "migrations")


def _ensure_migrations_table(conn):
    """Create the migrations tracking table if it doesn't exist."""
    cur = conn.cursor()
    try:
        cur.execute(f"""
            CREATE TABLE {t("JIVO_WA_MIGRATIONS")} (
                "Name"      NVARCHAR(200) NOT NULL PRIMARY KEY,
                "AppliedAt" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        log_hana.info("Created JIVO_WA_MIGRATIONS tracking table")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            log_hana.debug("JIVO_WA_MIGRATIONS table already exists")
        else:
            log_hana.warning("Migration table create warning: %s", e)
    finally:
        cur.close()


def _get_applied(conn) -> set[str]:
    """Return set of already-applied migration names."""
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT "Name" FROM {t("JIVO_WA_MIGRATIONS")}')
        return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()
    finally:
        cur.close()


def run_migrations():
    """Run all pending SQL migrations from migrations/ directory."""
    if not os.path.isdir(MIGRATIONS_DIR):
        log_hana.info("No migrations directory found, skipping")
        return

    conn = get_conn()
    try:
        _ensure_migrations_table(conn)
        applied = _get_applied(conn)

        from app.config import HANA_SCHEMA
        sql_files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql"))

        for filename in sql_files:
            if filename in applied:
                log_hana.debug("Migration %s already applied, skipping", filename)
                continue

            path = os.path.join(MIGRATIONS_DIR, filename)
            with open(path) as f:
                sql = f.read().replace("{schema}", HANA_SCHEMA)

            cur = conn.cursor()
            try:
                for statement in sql.split(";"):
                    statement = statement.strip()
                    if statement and not statement.startswith("--"):
                        cur.execute(statement)

                # Record migration as applied
                cur.execute(
                    f'INSERT INTO {t("JIVO_WA_MIGRATIONS")} ("Name") VALUES (?)',
                    (filename,),
                )
                conn.commit()
                log_hana.info("Applied migration: %s", filename)
            except Exception as e:
                conn.rollback()
                log_hana.warning("Migration %s skipped or failed: %s", filename, e)
            finally:
                cur.close()
    finally:
        release_conn(conn)
