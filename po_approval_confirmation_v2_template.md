# po_approval_confirmation_v2 — Template Redesign

## Problem

The current `po_approval_confirmation_v2` template only sends:
- WDD Code
- Document Type
- Action (APPROVED/REJECTED)
- Timestamp

Recipients don't know **which PO** was approved — no vendor name, PO number, amount, or who raised it. This makes the confirmation message almost useless without cross-referencing SAP manually.

---

## Current Template (4 parameters)

```
*PO Action Confirmed*

*WDD Code:* {{wdd_code}}
*Document Type:* {{doc_type}}
*Action:* {{action}}
*Time:* {{time}}

Your action has been successfully recorded in SAP.
```

---

## Proposed New Template (8 parameters)

```
*PO Action Confirmed* ✅

*WDD Code:* {{wdd_code}}
*PO Number:* {{po_number}}
*Document Type:* {{doc_type}}
*Vendor:* {{vendor}}
*Total Amount:* ₹{{amount}}
*Raised By:* {{raised_by}}

*Action:* {{action}}
*Time:* {{time}}

This action has been successfully recorded in SAP.
```

---

## Parameter Mapping

| #  | Name       | Description                          | Example                  | Source Field (DB)        |
|----|------------|--------------------------------------|--------------------------|--------------------------|
| 1  | wdd_code   | Unique WDD Code from SAP             | `"1234"`                 | `WddCode`               |
| 2  | po_number  | Purchase Order number                | `"PO-2024-001"`          | `PONumber`               |
| 3  | doc_type   | Human-readable document type         | `"Purchase Order"`       | `ObjType` (mapped)       |
| 4  | vendor     | Business Partner / Vendor name       | `"ABC Supplies"`         | `BPName`                 |
| 5  | amount     | Formatted total amount (no decimals) | `"1,250"`                | `TotalAmount` (formatted)|
| 6  | raised_by  | Name of PO creator                   | `"John Doe"`             | `CreatedBy`              |
| 7  | action     | Action taken                         | `"APPROVED"` / `"REJECTED"` | Derived from button  |
| 8  | time       | Timestamp of action                  | `"24 Mar 2026, 10:30 AM"` | Generated at send time |

---

## Meta Template Configuration

| Field         | Value                          |
|---------------|--------------------------------|
| Template Name | `po_approval_confirmation_v2`  |
| Category      | UTILITY                        |
| Language      | English (`en`)                 |
| Buttons       | None                           |

---

## Code Changes Required

### 1. `app/whatsapp/sender.py` — `send_confirmation_message()`

Need to accept and pass the new parameters:

```python
def send_confirmation_message(wdd_code: int, action: str,
                              doc_type: str, success: bool,
                              po_number: str = "", vendor: str = "",
                              amount: str = "", raised_by: str = ""):
```

Update the `parameters` list in the payload:

```python
"parameters": [
    {"type": "text", "parameter_name": "wdd_code", "text": str(wdd_code)},
    {"type": "text", "parameter_name": "po_number", "text": po_number},
    {"type": "text", "parameter_name": "doc_type", "text": doc_type},
    {"type": "text", "parameter_name": "vendor", "text": vendor},
    {"type": "text", "parameter_name": "amount", "text": amount},
    {"type": "text", "parameter_name": "raised_by", "text": raised_by},
    {"type": "text", "parameter_name": "action", "text": status_text},
    {"type": "text", "parameter_name": "time", "text": time_str},
],
```

### 2. `app/routes/webhook.py` — WhatsApp button handler

Pass PO details from the pending approval data when calling `send_confirmation_message()`.

### 3. `app/routes/api.py` — Dashboard approval handler

Same as above — pass PO details when calling `send_confirmation_message()`.

### 4. Meta Business Suite

Update the template body in Meta Business Suite with the new text and 8 parameters.

---

## Notes

- All new fields (po_number, vendor, amount, raised_by) are already available in the `view_whatsapp_bot` SAP view and fetched by `get_pending_approvals()`.
- The webhook handler will need to fetch PO details before sending confirmation (currently it only has `wdd_code`, `action`, `doc_type` from the button payload).
- No DB schema changes required.
