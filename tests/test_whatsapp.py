"""Tests for WhatsApp message sending."""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

WA_AVAILABLE = all(os.getenv(k) for k in ("WA_ACCESS_TOKEN", "WA_PHONE_NUMBER_ID", "APPROVER_PHONE"))


@pytest.mark.skipif(not WA_AVAILABLE, reason="WhatsApp credentials not configured")
class TestWhatsAppSend:

    def test_send_approval_template(self):
        """Verify approval template can be sent to first approver phone."""
        import httpx

        from app.config import WA_TOKEN, WA_PHONE_ID, APPROVER_PHONES, TEMPLATE_NAME

        url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WA_TOKEN}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": APPROVER_PHONES[0],
            "type": "template",
            "template": {
                "name": TEMPLATE_NAME,
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "parameter_name": "wdd_code", "text": "99999"},
                            {"type": "text", "parameter_name": "doc_type", "text": "Purchase Order"},
                            {"type": "text", "parameter_name": "vendor", "text": "Test Vendor"},
                            {"type": "text", "parameter_name": "po_number", "text": "TEST-001"},
                            {"type": "text", "parameter_name": "amount", "text": "1,000"},
                            {"type": "text", "parameter_name": "raised_by", "text": "Test User"},
                            {"type": "text", "parameter_name": "items", "text": "2 item(s)"},
                        ],
                    },
                    {
                        "type": "button", "sub_type": "quick_reply", "index": "0",
                        "parameters": [{"type": "payload", "payload": "APPROVE_99999"}],
                    },
                    {
                        "type": "button", "sub_type": "quick_reply", "index": "1",
                        "parameters": [{"type": "payload", "payload": "REJECT_99999"}],
                    },
                ],
            },
        }

        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


class TestSanitizeParam:

    def test_removes_newlines(self):
        from app.whatsapp.sender import _sanitize_param
        assert _sanitize_param("hello\nworld") == "hello world"

    def test_removes_tabs(self):
        from app.whatsapp.sender import _sanitize_param
        assert _sanitize_param("hello\tworld") == "hello world"

    def test_collapses_spaces(self):
        from app.whatsapp.sender import _sanitize_param
        assert _sanitize_param("hello      world") == "hello   world"

    def test_strips_whitespace(self):
        from app.whatsapp.sender import _sanitize_param
        assert _sanitize_param("  hello  ") == "hello"


class TestDocTypeMapping:

    def test_known_type(self):
        from app.whatsapp.constants import map_doc_type
        assert map_doc_type("22") == "Purchase Order"

    def test_unknown_type(self):
        from app.whatsapp.constants import map_doc_type
        result = map_doc_type("99999")
        assert "99999" in result


class TestStats:

    def test_increment_stat(self):
        from app.stats import increment_stat, get_stats_snapshot
        before = get_stats_snapshot()["polls"]
        increment_stat("polls")
        after = get_stats_snapshot()["polls"]
        assert after == before + 1

    def test_add_activity(self):
        from app.stats import add_activity, get_stats_snapshot
        add_activity("TEST", "unit test event")
        snapshot = get_stats_snapshot()
        assert len(snapshot["recent_activity"]) > 0
        assert snapshot["recent_activity"][0]["type"] == "TEST"

    def test_activity_max_size(self):
        from app.stats import add_activity, get_stats_snapshot, MAX_RECENT
        for i in range(MAX_RECENT + 10):
            add_activity("FILL", f"event {i}")
        snapshot = get_stats_snapshot()
        assert len(snapshot["recent_activity"]) <= MAX_RECENT
