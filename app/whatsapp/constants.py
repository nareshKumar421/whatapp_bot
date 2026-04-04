OBJ_TYPE_MAP: dict[str, str] = {
    "540000006": "Purchase Quotation",
    "22": "Purchase Order",
    "20": "Goods Receipt PO",
    "1470000113": "Goods Returns Request",
    "21": "Goods Returns",
    "204": "A/P Down Payment",
    "18": "A/P Invoice",
    "19": "A/P Credit Memo",
    "112": "Purchase Request",
    "1250000001": "Internal Requisition",
    "23": "Sales Quotation",
    "17": "Sales Order",
    "15": "Delivery",
    "13": "A/R Invoice",
    "14": "A/R Credit Memo",
    "203": "A/R Down Payment",
    "59": "Goods Receipt",
    "60": "Goods Issue",
    "67": "Inventory Transfer",
    "67001": "Inventory Transfer Request",
    "69": "Inventory Opening Balance",
    "165": "Inventory Counting",
    "163": "Inventory Posting",
    "24": "Incoming Payment",
    "46": "Outgoing Payment",
}


def map_doc_type(obj_type: str) -> str:
    return OBJ_TYPE_MAP.get(str(obj_type), f"Document (Type {obj_type})")
