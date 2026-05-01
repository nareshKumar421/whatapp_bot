# PO Item Details Template (with MRP)

> **Template Name:** `po_item_details` (updated version with MRP)
> **Category:** UTILITY
> **Language:** English (en)
> **API Version:** WhatsApp Cloud API v19.0

---

## Template Body

```
*Item Details*

*Code:* {{code}}
*Name:* {{name}}
*Demand Qty:* {{demand}}
*In Stock:* {{instock}}
*Benchmark:* {{benchmark}}
*MRP:* {{mrp}}
```

---

## Parameters

| #  | Parameter Name | Description                              | Example Value |
|----|---------------|------------------------------------------|---------------|
| 1  | `code`        | Item code from SAP                       | `A00001`      |
| 2  | `name`        | Item name / description                  | `Copper Wire` |
| 3  | `demand`      | PO quantity (formatted with commas)      | `1,500`       |
| 4  | `instock`     | Current stock level                      | `3,200`       |
| 5  | `benchmark`   | Minimum stock / benchmark level          | `500`         |
| 6  | `mrp`         | MRP (Maximum Retail Price / Material Resource Planning value) | `2,750` |

---

## Sending Logic

- One message is sent **per item** to avoid character-limit issues.
- Sent to all `APPROVER_PHONES` immediately after the main PO approval request template.
- Numeric values (`demand`, `instock`, `benchmark`, `mrp`) are formatted with commas and no decimals (e.g., `1,250`).
- All text parameters are sanitized (no newlines, tabs, or 4+ consecutive spaces).
- Automatic retry: 3 attempts with exponential backoff on transient failures.

---

## Environment Variable

```
WA_ITEMS_TEMPLATE=po_item_details
```

---

## Meta Business Manager Setup

To use this template, you must register it in **Meta Business Manager** with:

1. Go to **WhatsApp Manager > Message Templates**
2. Create or update the template named `po_item_details`
3. Set the body text as shown above with **6 parameters**: `code`, `name`, `demand`, `instock`, `benchmark`, `mrp`
4. Submit for approval

---

## Source (view_whatsapp_bot)

The MRP value is sourced from the `"MRP"` column in the `view_whatsapp_bot` SAP HANA view. Ensure this column is present in the view definition.

### Columns used per item:

| View Column       | Maps to Parameter |
|-------------------|-------------------|
| `ItemCode`        | `code`            |
| `ItemName`        | `name`            |
| `POQuantity`      | `demand`          |
| `CurrentStock`    | `instock`         |
| `MinimumStock`    | `benchmark`       |
| `MRP`             | `mrp`             |
