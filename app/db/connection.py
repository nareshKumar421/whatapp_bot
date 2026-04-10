import threading

from hdbcli import dbapi

from app.config import HANA_HOST, HANA_PORT, HANA_USER, HANA_PASS, HANA_SCHEMA
from app.logging_setup import log_hana

_lock = threading.Lock()
_pool: list[dbapi.Connection] = []
_MAX_POOL = 5


def get_conn() -> dbapi.Connection:
    """Return a HANA connection, reusing from pool when possible."""
    with _lock:
        while _pool:
            conn = _pool.pop()
            try:
                if conn.isconnected():
                    log_hana.debug("Reusing pooled HANA connection (%d remaining)", len(_pool))
                    return conn
            except Exception:
                pass

    log_hana.debug("Opening new HANA connection to %s:%s", HANA_HOST, HANA_PORT)
    return dbapi.connect(
        address=HANA_HOST,
        port=HANA_PORT,
        user=HANA_USER,
        password=HANA_PASS,
    )


def release_conn(conn: dbapi.Connection):
    """Return a connection to the pool instead of closing it."""
    try:
        if conn.isconnected():
            with _lock:
                if len(_pool) < _MAX_POOL:
                    _pool.append(conn)
                    log_hana.debug("Returned connection to pool (%d total)", len(_pool))
                    return
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def t(table: str) -> str:
    """Return schema-qualified quoted table name."""
    return f'"{HANA_SCHEMA}"."{table}"'
