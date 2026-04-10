"""Tests for SAP HANA connectivity and pending approval queries."""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

HANA_AVAILABLE = all(os.getenv(k) for k in ("HANA_HOST", "HANA_USER", "HANA_PASS", "HANA_SCHEMA"))


@pytest.mark.skipif(not HANA_AVAILABLE, reason="HANA credentials not configured")
class TestHanaConnection:

    def test_connect(self):
        """Verify HANA connection can be established."""
        from hdbcli import dbapi

        conn = dbapi.connect(
            address=os.getenv("HANA_HOST"),
            port=int(os.getenv("HANA_PORT", 30015)),
            user=os.getenv("HANA_USER"),
            password=os.getenv("HANA_PASS"),
        )
        assert conn.isconnected()
        conn.close()

    def test_pending_approvals_query(self):
        """Verify pending approvals query runs without error."""
        from app.db.queries import get_pending_approvals

        results = get_pending_approvals()
        assert isinstance(results, list)
        for item in results:
            assert "WddCode" in item
            assert "items" in item
            assert isinstance(item["items"], list)

    def test_sent_count(self):
        """Verify sent count query returns an integer."""
        from app.db.tracking import get_sent_count

        count = get_sent_count()
        assert isinstance(count, int)
        assert count >= 0
