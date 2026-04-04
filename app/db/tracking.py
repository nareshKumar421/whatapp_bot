from app.db.connection import get_conn, t
from app.logging_setup import log_hana
from app.stats import stats


def create_tracking_table():
    """Create JIVO_WA_SENT table if it does not exist."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            CREATE TABLE {t("JIVO_WA_SENT")} (
                "WddCode"   INTEGER      NOT NULL PRIMARY KEY,
                "SentAt"    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                "Status"    NVARCHAR(20) DEFAULT 'PENDING'
            )
        """)
        conn.commit()
        log_hana.info("Created JIVO_WA_SENT tracking table")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate table name" in str(e).lower():
            log_hana.info("JIVO_WA_SENT table already exists")
        else:
            log_hana.warning("Table create warning: %s", e)
    finally:
        cur.close()
        conn.close()


def is_already_sent(wdd_code: int) -> bool:
    """Check whether WddCode has already been sent."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f'SELECT COUNT(*) FROM {t("JIVO_WA_SENT")} WHERE "WddCode" = ?',
            (wdd_code,),
        )
        return cur.fetchone()[0] > 0
    except Exception as e:
        log_hana.error("Error checking sent status for WddCode=%s: %s", wdd_code, e)
        stats["hana_errors"] += 1
        return False
    finally:
        cur.close()
        conn.close()


def mark_as_sent(wdd_code: int):
    """Record WddCode in HANA tracking table."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            INSERT INTO {t("JIVO_WA_SENT")} ("WddCode", "SentAt", "Status")
            VALUES (?, CURRENT_TIMESTAMP, 'PENDING')
        """, (wdd_code,))
        conn.commit()
        log_hana.info("Marked WddCode=%s as sent in JIVO_WA_SENT", wdd_code)
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            log_hana.debug("WddCode=%s already in JIVO_WA_SENT (duplicate)", wdd_code)
        else:
            log_hana.error("Error marking WddCode=%s as sent: %s", wdd_code, e)
            stats["hana_errors"] += 1
    finally:
        cur.close()
        conn.close()


def get_sent_count() -> int:
    """Get count of rows in JIVO_WA_SENT."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT COUNT(*) FROM {t("JIVO_WA_SENT")}')
        return cur.fetchone()[0]
    except Exception:
        return 0
    finally:
        cur.close()
        conn.close()


def get_sent_records() -> list[dict]:
    """Get all records from JIVO_WA_SENT for dashboard."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f'SELECT "WddCode", "SentAt", "Status" FROM {t("JIVO_WA_SENT")} ORDER BY "SentAt" DESC'
        )
        cols = [col[0] for col in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        cur.close()
        conn.close()
