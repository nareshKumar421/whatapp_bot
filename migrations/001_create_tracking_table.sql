-- Migration 001: Create JIVO_WA_SENT tracking table
CREATE TABLE "{schema}"."JIVO_WA_SENT" (
    "WddCode"    INTEGER      NOT NULL PRIMARY KEY,
    "SentAt"     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    "Status"     NVARCHAR(20) DEFAULT 'PENDING',
    "ApprovedBy" NVARCHAR(100) DEFAULT '',
    "Source"     NVARCHAR(20)  DEFAULT '',
    "ActionAt"   TIMESTAMP     NULL
);
