# Run this first to verify HANA connectivity and check pending approvals.
# python test_hana.py

import os
from dotenv import load_dotenv
from hdbcli import dbapi

load_dotenv()

SCHEMA = os.getenv("HANA_SCHEMA")

conn = dbapi.connect(
    address=os.getenv("HANA_HOST"),
    port=int(os.getenv("HANA_PORT", 30015)),
    user=os.getenv("HANA_USER"),
    password=os.getenv("HANA_PASS")
)
print("✓ HANA connected successfully.\n")

cur = conn.cursor()

# Check pending Purchase Order approvals
cur.execute(f"""
    SELECT
        w."WddCode",
        w."ObjType",
        w."DraftEntry",
        d."CardName"  AS "BPName",
        d."DocTotal"  AS "TotalAmount",
        creator."U_NAME" AS "CreatedBy"
    FROM "{SCHEMA}"."OWDD" w
    INNER JOIN "{SCHEMA}"."WDD1" w1
        ON  w."WddCode" = w1."WddCode"
    INNER JOIN "{SCHEMA}"."OUSR" creator
        ON  w."OwnerID" = creator."USERID"
    LEFT  JOIN "{SCHEMA}"."ODRF" d
        ON  w."DraftEntry" = d."DocEntry"
        AND w."ObjType"    = d."ObjType"
    WHERE w."ProcesStat" = 'W'
      AND w1."Status"    = 'W'
      AND w."ObjType"    = '22'
""")

rows = cur.fetchall()
print(f"Pending PO approvals: {len(rows)}\n")
for r in rows:
    print(f"  WddCode={r[0]} | DraftEntry={r[2]} | "
          f"Vendor={r[3]} | ₹{(r[4] or 0):,.0f} | By={r[5]}")

cur.close()
conn.close()