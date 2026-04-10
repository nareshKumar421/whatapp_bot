from datetime import datetime
from typing import Optional

from app.db.connection import get_conn, release_conn, t
from app.logging_setup import log_hana
from app.stats import increment_stat


def get_pending_approvals() -> list[dict]:
    """Returns pending PO approvals from view_whatsapp_bot, grouped by WddCode.

    Each returned dict has header fields plus an 'items' list containing
    ItemCode, ItemName, POQuantity, RequiredPlannedQty, CurrentStock, MinimumStock.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT
                "WddCode", "DraftEntry", "ObjType", "OwnerID",
                "ApproverID", "ApproverName", "ApproverEmail",
                "CreatedBy", "BPName", "PONumber", "TotalAmount", "Comments",
                "ItemCode", "ItemName", "POQuantity",
                "RequiredPlannedQty", "CurrentStock", "MinimumStock"
            FROM {t("view_whatsapp_bot")}
        """)
        cols = [col[0] for col in cur.description]
        raw_rows = [dict(zip(cols, row)) for row in cur.fetchall()]

        # Group rows by WddCode
        grouped: dict[int, dict] = {}
        for row in raw_rows:
            wdd = row["WddCode"]
            if wdd not in grouped:
                grouped[wdd] = {
                    "WddCode": wdd,
                    "DraftEntry": row["DraftEntry"],
                    "ObjType": row["ObjType"],
                    "OwnerID": row["OwnerID"],
                    "ApproverID": row["ApproverID"],
                    "ApproverName": row["ApproverName"],
                    "ApproverEmail": row["ApproverEmail"],
                    "CreatedBy": row["CreatedBy"],
                    "BPName": row["BPName"],
                    "PONumber": row["PONumber"],
                    "TotalAmount": row["TotalAmount"],
                    "Comments": row["Comments"],
                    "items": [],
                }
            grouped[wdd]["items"].append({
                "ItemCode": row["ItemCode"],
                "ItemName": row["ItemName"],
                "POQuantity": row["POQuantity"],
                "RequiredPlannedQty": row["RequiredPlannedQty"],
                "CurrentStock": row["CurrentStock"],
                "MinimumStock": row["MinimumStock"],
            })

        results = list(grouped.values())
        log_hana.info("Fetched %d pending approvals (%d total rows) from view", len(results), len(raw_rows))
        return results
    except Exception as e:
        log_hana.error("Error fetching pending approvals: %s", e)
        increment_stat("hana_errors")
        raise
    finally:
        cur.close()
        release_conn(conn)


def get_po_details(wdd_code: int) -> Optional[dict]:
    """Returns PO header details (BPName, PONumber, TotalAmount, CreatedBy) for a given WddCode."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT "BPName", "PONumber", "TotalAmount", "CreatedBy"
            FROM   {t("view_whatsapp_bot")}
            WHERE  "WddCode" = ?
            FETCH FIRST 1 ROWS ONLY
        """, (wdd_code,))
        row = cur.fetchone()
        if not row:
            log_hana.warning("WddCode=%s not found in view_whatsapp_bot", wdd_code)
            return None
        return {
            "BPName": row[0] or "N/A",
            "PONumber": row[1] or "N/A",
            "TotalAmount": row[2] or 0,
            "CreatedBy": row[3] or "N/A",
        }
    finally:
        cur.close()
        release_conn(conn)


def get_wdd_status(wdd_code: int) -> Optional[dict]:
    """Returns OWDD row for given WddCode, or None if not found."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT "WddCode", "ProcesStat", "DraftEntry", "ObjType"
            FROM   {t("OWDD")}
            WHERE  "WddCode" = ?
        """, (wdd_code,))
        row = cur.fetchone()
        if not row:
            log_hana.warning("WddCode=%s not found in OWDD", wdd_code)
            return None
        log_hana.debug("WddCode=%s status: ProcesStat=%s", wdd_code, row[1])
        return {
            "WddCode": row[0],
            "ProcesStat": row[1],
            "DraftEntry": row[2],
            "ObjType": row[3],
        }
    finally:
        cur.close()
        release_conn(conn)


def apply_approval_decision(wdd_code: int, action: str, remarks: str = "",
                            source: str = "WhatsApp", approved_by: str = "") -> dict:
    """Apply approval/rejection in a single transaction across all SAP tables.

    action must be 'APPROVE' or 'REJECT'.
    source: 'WhatsApp' or 'Dashboard'
    approved_by: phone number or dashboard username
    """
    wdd = get_wdd_status(wdd_code)

    if wdd is None:
        log_hana.error("WddCode=%s not found for %s", wdd_code, action)
        return {"success": False, "message": f"WddCode {wdd_code} not found in SAP."}

    if wdd["ProcesStat"] != "W":
        log_hana.warning("WddCode=%s already processed (status=%s)", wdd_code, wdd["ProcesStat"])
        return {
            "success": False,
            "message": f"Already processed. Current status: {wdd['ProcesStat']}",
        }

    new_status = "Y" if action == "APPROVE" else "N"
    remark_text = remarks if remarks else (
        f"{'Approved' if action == 'APPROVE' else 'Rejected'} via {source}."
    )
    approval_date = datetime.now().strftime("%Y-%m-%d")
    approval_time = int(datetime.now().strftime("%H%M"))
    draft_entry = wdd["DraftEntry"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        # All updates in a single transaction
        cur.execute(f"""
            UPDATE {t("OWDD")}
            SET "ProcesStat" = ?,
                "Status"     = ?,
                "Remarks"    = ?
            WHERE "WddCode"  = ?
        """, (new_status, new_status, remark_text, wdd_code))
        log_hana.info("Updated OWDD: WddCode=%s -> %s (via %s)", wdd_code, new_status, source)

        cur.execute(f"""
            UPDATE {t("WDD1")}
            SET "Status"     = ?,
                "UpdateDate" = ?,
                "UpdateTime" = ?,
                "Remarks"    = ?
            WHERE "WddCode"  = ?
              AND "Status"  IN ('P', 'W')
        """, (new_status, approval_date, approval_time, remark_text, wdd_code))
        log_hana.info("Updated WDD1: WddCode=%s -> %s", wdd_code, new_status)

        if action == "APPROVE":
            cur.execute(f"""
                UPDATE {t("ODRF")}
                SET "WddStatus" = 'A'
                WHERE "DocEntry" = ?
            """, (draft_entry,))
            log_hana.info("Updated ODRF: DocEntry=%s -> WddStatus=A", draft_entry)

        cur.execute(f"""
            UPDATE {t("JIVO_WA_SENT")}
            SET "Status"     = ?,
                "ApprovedBy" = ?,
                "Source"     = ?,
                "ActionAt"   = CURRENT_TIMESTAMP
            WHERE "WddCode"  = ?
        """, (action, approved_by, source, wdd_code))

        # Single commit for all updates
        conn.commit()

        log_hana.info("WddCode=%s %sD successfully in SAP B1 (source=%s, by=%s)",
                      wdd_code, action, source, approved_by)
        return {
            "success": True,
            "message": f"WddCode={wdd_code} {action}D successfully.",
            "doc_type": wdd.get("ObjType", "22"),
        }

    except Exception as e:
        try:
            conn.rollback()
        except Exception as rb_err:
            log_hana.warning("Rollback failed for WddCode=%s: %s", wdd_code, rb_err)
        log_hana.error("DB error for WddCode=%s: %s", wdd_code, e)
        increment_stat("hana_errors")
        return {"success": False, "message": f"DB error: {str(e)}"}
    finally:
        cur.close()
        release_conn(conn)
