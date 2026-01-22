# Testing Audit Trail - Complete Workflow

This guide will walk you through the complete workflow to populate and verify the audit trail.

## Prerequisites

Make sure the server is running:
```bash
# From c:\Work\portfolio\mockdata
python app.py
```

Server should start on http://localhost:8000

---

## Step 1: Verify Server is Running

```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-01-22T10:30:45.123456"
}
```

---

## Step 2: Check Initial Audit State (should be empty)

```bash
curl -s "http://localhost:8000/audit?page_size=50" | python -m json.tool
```

**Expected Response:**
```json
{
  "total": 0,
  "page": 1,
  "page_size": 50,
  "items": []
}
```

✅ **Correct** - No operations logged yet

---

## Step 3: Import Bank Transactions

```bash
$form = @{ file = Get-Item "case/reconciliation/bank_transactions.csv" }; 
Invoke-WebRequest -Uri "http://localhost:8000/imports/bank" -Form $form -Method Post | 
Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json -Depth 3
```

**Expected Response:**
```json
{
  "import_batch_id": "batch_20260122_102345_abc12345",
  "total_rows": 20,
  "imported": 18,
  "skipped_duplicates": 1,
  "failed": 1,
  "errors": [
    {
      "row": 17,
      "txn_id": "BNK-2026-000017",
      "error": "Invalid amount: NOT_A_NUMBER"
    }
  ],
  "created_at": "2026-01-22T10:35:20.123456"
}
```

✅ **Success** - Bank transactions imported + audit event created

---

## Step 4: Check Audit After Bank Import

```bash
curl -s "http://localhost:8000/audit?event_type=import_bank_transactions&page_size=50" | python -m json.tool
```

**Expected Response:**
```json
{
  "total": 1,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "id": 1,
      "timestamp": "2026-01-22T10:35:20.123456",
      "actor_type": "system",
      "actor_id": "csv_import",
      "event_type": "import_bank_transactions",
      "entity_type": "bank_transaction",
      "entity_id": "batch_20260122_102345_abc12345",
      "metadata_json": {
        "batch_id": "batch_20260122_102345_abc12345",
        "imported": 18,
        "skipped": 1,
        "failed": 1,
        "filename": "bank_transactions.csv"
      },
      "before_state": null,
      "after_state": null
    }
  ]
}
```

✅ **Success** - Audit event logged with import details

---

## Step 5: Import Invoices

```bash
$form = @{ file = Get-Item "case/reconciliation/ar_invoices.csv" }; 
Invoke-WebRequest -Uri "http://localhost:8000/imports/ar" -Form $form -Method Post | 
Select-Object -ExpandProperty Content | ConvertFrom-Json | ConvertTo-Json -Depth 3
```

**Expected Response:**
```json
{
  "import_batch_id": "batch_20260122_103100_def67890",
  "total_rows": 11,
  "imported": 11,
  "skipped_duplicates": 0,
  "failed": 0,
  "errors": [],
  "created_at": "2026-01-22T10:31:00.123456"
}
```

✅ **Success** - All invoices imported

---

## Step 6: Check Audit After Invoice Import

```bash
curl -s "http://localhost:8000/audit?page_size=50" | python -m json.tool
```

**Expected Response:**
```json
{
  "total": 2,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "id": 2,
      "timestamp": "2026-01-22T10:31:00.123456",
      "actor_type": "system",
      "actor_id": "csv_import",
      "event_type": "import_invoices",
      "entity_type": "invoice",
      "entity_id": "batch_20260122_103100_def67890",
      "metadata_json": {
        "batch_id": "batch_20260122_103100_def67890",
        "imported": 11,
        "skipped": 0,
        "failed": 0,
        "filename": "ar_invoices.csv"
      },
      "before_state": null,
      "after_state": null
    },
    {
      "id": 1,
      "timestamp": "2026-01-22T10:35:20.123456",
      "actor_type": "system",
      "actor_id": "csv_import",
      "event_type": "import_bank_transactions",
      "entity_type": "bank_transaction",
      "entity_id": "batch_20260122_102345_abc12345",
      "metadata_json": {
        "batch_id": "batch_20260122_102345_abc12345",
        "imported": 18,
        "skipped": 1,
        "failed": 1,
        "filename": "bank_transactions.csv"
      },
      "before_state": null,
      "after_state": null
    }
  ]
}
```

✅ **Success** - 2 audit events (newest first)

---

## Step 7: Run Reconciliation

```bash
curl -X POST http://localhost:8000/reconcile/suggest `
  -H "Content-Type: application/json" `
  -d '{"rule_version": "v1"}' | python -m json.tool
```

**Expected Response:**
```json
{
  "rule_version": "v1",
  "suggestions_created": 15,
  "suggestions_skipped": 0,
  "timestamp": "2026-01-22T10:32:15.123456"
}
```

✅ **Success** - 15 reconciliation suggestions created

---

## Step 8: Check Audit After Reconciliation

```bash
curl -s "http://localhost:8000/audit?event_type=reconciliation_run&page_size=50" | python -m json.tool
```

**Expected Response:**
```json
{
  "total": 1,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "id": 3,
      "timestamp": "2026-01-22T10:32:15.123456",
      "actor_type": "system",
      "actor_id": "reconciliation_engine",
      "event_type": "reconciliation_run",
      "entity_type": "reconciliation_suggestion",
      "entity_id": null,
      "metadata_json": {
        "rule_version": "v1",
        "suggestions_created": 15,
        "suggestions_skipped": 0
      },
      "before_state": null,
      "after_state": null
    }
  ]
}
```

✅ **Success** - Reconciliation event logged

---

## Step 9: View Pending Suggestions

```bash
curl -s "http://localhost:8000/reconciliation-suggestions?status=pending&page_size=20" | python -m json.tool
```

**Expected Response:**
```json
{
  "total": 15,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "suggestion_key": "abc123def456xyz789...",
      "txn_id": "BNK-2026-000001",
      "invoice_id": "INV-2026-0001",
      "rule_version": "v1",
      "confidence": "0.95",
      "reason": "Exact match: amount and date",
      "status": "pending",
      "created_at": "2026-01-22T10:32:15.123456"
    },
    ...
  ]
}
```

✅ **Success** - 15 pending suggestions ready for approval

---

## Step 10: Approve Suggestions

```bash
curl -X POST http://localhost:8000/reconcile/approve `
  -H "Content-Type: application/json" `
  -d '{"suggestion_ids": [1, 2, 3, 4, 5]}' | python -m json.tool
```

**Expected Response:**
```json
{
  "approved": 5,
  "timestamp": "2026-01-22T10:33:00.123456"
}
```

✅ **Success** - 5 suggestions approved + audit events created

---

## Step 11: Check Full Audit Trail

```bash
curl -s "http://localhost:8000/audit?page_size=100" | python -m json.tool
```

**Expected Response (multiple events):**
```json
{
  "total": 8,
  "page": 1,
  "page_size": 100,
  "items": [
    {
      "id": 8,
      "timestamp": "2026-01-22T10:33:00.123456",
      "actor_type": "user",
      "actor_id": "test@mail.com",
      "event_type": "suggestion_approved",
      "entity_type": "reconciliation_suggestion",
      "entity_id": "5",
      "metadata_json": {
        "suggestion_id": 5,
        "txn_id": "BNK-2026-000005",
        "invoice_id": "INV-2026-0005"
      },
      "before_state": null,
      "after_state": null
    },
    {
      "id": 7,
      "timestamp": "2026-01-22T10:33:00.123456",
      "actor_type": "user",
      "actor_id": "test@mail.com",
      "event_type": "suggestion_approved",
      "entity_type": "reconciliation_suggestion",
      "entity_id": "4",
      "metadata_json": {
        "suggestion_id": 4,
        "txn_id": "BNK-2026-000004",
        "invoice_id": "INV-2026-0004"
      },
      "before_state": null,
      "after_state": null
    },
    {
      "id": 6,
      "timestamp": "2026-01-22T10:33:00.123456",
      "actor_type": "user",
      "actor_id": "test@mail.com",
      "event_type": "suggestion_approved",
      "entity_type": "reconciliation_suggestion",
      "entity_id": "3",
      "metadata_json": {
        "suggestion_id": 3,
        "txn_id": "BNK-2026-000003",
        "invoice_id": "INV-2026-0003"
      },
      "before_state": null,
      "after_state": null
    },
    {
      "id": 5,
      "timestamp": "2026-01-22T10:33:00.123456",
      "actor_type": "user",
      "actor_id": "test@mail.com",
      "event_type": "suggestion_approved",
      "entity_type": "reconciliation_suggestion",
      "entity_id": "2",
      "metadata_json": {
        "suggestion_id": 2,
        "txn_id": "BNK-2026-000002",
        "invoice_id": "INV-2026-0002"
      },
      "before_state": null,
      "after_state": null
    },
    {
      "id": 4,
      "timestamp": "2026-01-22T10:33:00.123456",
      "actor_type": "user",
      "actor_id": "test@mail.com",
      "event_type": "suggestion_approved",
      "entity_type": "reconciliation_suggestion",
      "entity_id": "1",
      "metadata_json": {
        "suggestion_id": 1,
        "txn_id": "BNK-2026-000001",
        "invoice_id": "INV-2026-0001"
      },
      "before_state": null,
      "after_state": null
    },
    {
      "id": 3,
      "timestamp": "2026-01-22T10:32:15.123456",
      "actor_type": "system",
      "actor_id": "reconciliation_engine",
      "event_type": "reconciliation_run",
      "entity_type": "reconciliation_suggestion",
      "entity_id": null,
      "metadata_json": {
        "rule_version": "v1",
        "suggestions_created": 15,
        "suggestions_skipped": 0
      },
      "before_state": null,
      "after_state": null
    },
    {
      "id": 2,
      "timestamp": "2026-01-22T10:31:00.123456",
      "actor_type": "system",
      "actor_id": "csv_import",
      "event_type": "import_invoices",
      "entity_type": "invoice",
      "entity_id": "batch_20260122_103100_def67890",
      "metadata_json": {
        "batch_id": "batch_20260122_103100_def67890",
        "imported": 11,
        "skipped": 0,
        "failed": 0,
        "filename": "ar_invoices.csv"
      },
      "before_state": null,
      "after_state": null
    },
    {
      "id": 1,
      "timestamp": "2026-01-22T10:35:20.123456",
      "actor_type": "system",
      "actor_id": "csv_import",
      "event_type": "import_bank_transactions",
      "entity_type": "bank_transaction",
      "entity_id": "batch_20260122_102345_abc12345",
      "metadata_json": {
        "batch_id": "batch_20260122_102345_abc12345",
        "imported": 18,
        "skipped": 1,
        "failed": 1,
        "filename": "bank_transactions.csv"
      },
      "before_state": null,
      "after_state": null
    }
  ]
}
```

✅ **Success** - Complete audit trail showing:
- 2 import events (bank + invoices)
- 1 reconciliation run event
- 5 approval events
- Chronological order (newest first)
- Complete metadata for each event

---

## What the Audit Trail Shows

| Event Type | When Logged | Details |
|------------|------------|---------|
| `import_bank_transactions` | CSV uploaded | batch_id, imported count, failed count, filename |
| `import_invoices` | CSV uploaded | batch_id, imported count, failed count, filename |
| `reconciliation_run` | Matching executed | rule_version, suggestions_created, suggestions_skipped |
| `suggestion_approved` | Operator approved match | suggestion_id, txn_id, invoice_id, actor_id |
| `import_conflict` | Duplicate ID with different content | batch_id, conflicting transaction |
| `import_row_failed` | CSV parsing error | row number, error reason |

---

## Useful Audit Queries

```bash
# View all imports
curl "http://localhost:8000/audit?event_type=import_bank_transactions"

# View all reconciliation runs
curl "http://localhost:8000/audit?event_type=reconciliation_run"

# View all approvals
curl "http://localhost:8000/audit?event_type=suggestion_approved"

# View all failed imports
curl "http://localhost:8000/audit?event_type=import_row_failed"

# View events by specific actor
curl "http://localhost:8000/audit?actor_id=test@mail.com"

# View last 100 events
curl "http://localhost:8000/audit?page_size=100"

# View page 2
curl "http://localhost:8000/audit?page=2&page_size=50"
```

---

## Summary

✅ **Audit trail is working correctly!**
- Initially empty (no events) = Correct
- After imports = Import events logged
- After reconciliation = Reconciliation event logged
- After approvals = Approval events logged
- Full metadata captured = Complete traceability

The empty response at the beginning is **expected** and **correct**. The audit trail populates as operations are performed.
