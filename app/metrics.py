from prometheus_client import Counter, Histogram, Info

# Application info
app_info = Info("wa_bot", "WhatsApp SAP B1 PO Approval Bot")
app_info.info({"version": "2.0.0"})

# Counters
messages_sent_total = Counter("wa_messages_sent_total", "Total WhatsApp messages sent", ["template"])
messages_failed_total = Counter("wa_messages_failed_total", "Total WhatsApp message failures", ["template"])
polls_total = Counter("wa_polls_total", "Total polling cycles executed")
approvals_total = Counter("wa_approvals_total", "Total POs approved", ["source"])
rejections_total = Counter("wa_rejections_total", "Total POs rejected", ["source"])
webhook_received_total = Counter("wa_webhook_received_total", "Total webhooks received")
webhook_errors_total = Counter("wa_webhook_errors_total", "Total webhook processing errors")
hana_errors_total = Counter("wa_hana_errors_total", "Total SAP HANA errors")

# Histograms
poll_duration_seconds = Histogram("wa_poll_duration_seconds", "Time spent polling HANA")
webhook_duration_seconds = Histogram("wa_webhook_duration_seconds", "Time spent processing webhooks")
