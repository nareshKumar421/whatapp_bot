from hdbcli import dbapi

from app.config import HANA_HOST, HANA_PORT, HANA_USER, HANA_PASS, HANA_SCHEMA
from app.logging_setup import log_hana


def get_conn() -> dbapi.Connection:
    """Open and return a HANA connection."""
    log_hana.debug("Opening HANA connection to %s:%s", HANA_HOST, HANA_PORT)
    return dbapi.connect(
        address=HANA_HOST,
        port=HANA_PORT,
        user=HANA_USER,
        password=HANA_PASS,
    )


def t(table: str) -> str:
    """Return schema-qualified quoted table name."""
    return f'"{HANA_SCHEMA}"."{table}"'
