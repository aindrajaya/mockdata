# Reconciliation Service Backend - Quick Reference

A FastAPI-based bank transaction and AR invoice reconciliation engine designed for production use with idempotent operations and full audit trail.

> **📖 For detailed documentation**, see [BACKEND_DOCUMENTATION.md](../BACKEND_DOCUMENTATION.md) - includes user flows, complete API reference, and troubleshooting.

## Quick Start

### Prerequisites
- Python 3.8+
- pip

### Installation

1. **Install dependencies**
   ```bash
   cd c:\Work\portfolio\mockdata
   pip install -r requirements.txt
   ```

2. **Configure database (optional)**
   Set environment variable for database URL. Defaults to SQLite if not set:
   ```bash
   # Windows PowerShell
   $env:DATABASE_URL="postgresql://user:password@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
   
   # Windows CMD
   set DATABASE_URL=postgresql://user:password@aws-1-ap-south-1.pooler.supabase.com:6543/postgres
   
   # Or create .env file in project root
   DATABASE_URL=postgresql://user:password@host:5432/db
   ```

3. **Run the server**
   ```bash
   # From project root
   python app.py
   ```

4. **Access the API**
   - **Swagger UI**: http://localhost:8000/docs
   - **ReDoc**: http://localhost:8000/redoc
   - **API Base**: http://localhost:8000
   - **OpenAPI Spec**: http://localhost:8000/openapi.json

### Testing

Run the test suite:
```bash
pytest app.py -v
```

## API Quick Reference

All endpoints are auto-documented at http://localhost:8000/docs (Swagger UI)

### Import Endpoints (2)

#### `POST /imports/bank` - Import Bank Transactions
Upload CSV file with bank transactions
```bash
curl -X POST http://localhost:8000/imports/bank \
  -F "file=@bank_transactions.csv"
```

**CSV Format:**
```csv
txn_id,txn_date,account_iban,counterparty_name,description,amount,currency,bank_reference
BNK-2026-000001,2026-01-02,DK5000400440116243,Acme A/S,Invoice INV-001,-2500.00,DKK,REF123
```

**Response:** `{import_batch_id, total_rows, imported, skipped_duplicates, failed, errors, created_at}`

#### `POST /imports/ar` - Import AR Invoices
Upload CSV file with invoices
```bash
curl -X POST http://localhost:8000/imports/ar \
  -F "file=@ar_invoices.csv"
```

**CSV Format:**
```csv
invoice_id,invoice_date,due_date,customer_id,customer_name,amount_gross,currency
INV-2026-0001,2025-12-28,2026-01-05,CUST-ACME,Acme A/S,2500.00,DKK
```

### Reconciliation Endpoints (2)

#### `POST /reconcile/suggest` - Run Matching Engine
```bash
curl -X POST http://localhost:8000/reconcile/suggest \
  -H "Content-Type: application/json" \
  -d '{"rule_version": "v1"}'
```

**Response:** `{rule_version, suggestions_created, suggestions_skipped, timestamp}`

#### `POST /reconcile/approve` - Approve Suggestions
```bash
curl -X POST http://localhost:8000/reconcile/approve \
  -H "Content-Type: application/json" \
  -d '{"suggestion_ids": [1, 2, 3]}'
```

**Response:** `{approved, timestamp}`

### Query Endpoints (5)

#### `GET /bank-transactions` - List Bank Transactions
```bash
curl "http://localhost:8000/bank-transactions?page=1&page_size=20&status=matched"
```

Filters: `status`, `currency`, `counterparty_name`, `txn_date_from`, `txn_date_to`, `page`, `page_size`

#### `GET /invoices` - List Invoices
```bash
curl "http://localhost:8000/invoices?page=1&page_size=20&status=open"
```

Filters: `status`, `currency`, `customer_name`, `invoice_date_from`, `invoice_date_to`, `page`, `page_size`

#### `GET /reconciliation-suggestions` - List Suggestions
```bash
curl "http://localhost:8000/reconciliation-suggestions?status=pending&page_size=50"
```

Filters: `status` (pending|approved|rejected), `page`, `page_size`

#### `GET /audit` - Audit Trail
```bash
curl "http://localhost:8000/audit?event_type=import_bank_transactions&page_size=100"
```

Filters: `event_type`, `actor_id`, `page`, `page_size` (max 200)

#### `GET /health` - Health Check
```bash
curl http://localhost:8000/health
```

Response: `{status, database, timestamp}`

---

## Key Features

#### 1. Idempotent CSV Ingestion
- **Bank Transactions:** Unique by `txn_id` - upload same file twice = zero duplicates
- **Invoices:** Unique by `invoice_id` - re-uploads are skipped
- **Error Resilience:** Invalid rows logged, valid rows committed (per-record commit)
- **Conflict Detection:** Different content with same ID logged as `import_conflict` event

#### 2. MVP Reconciliation Rules
Configurable matching engine with deterministic results:
- **Currency Match:** Exact match required (DKK, EUR, etc.)
- **Amount Tolerance:** ±0.05 (handles rounding: 1499.995 → 1500.00)
- **Date Window:** ±30 days from invoice date
- **Confidence Scoring:** 0.95 for exact, 0.75 for partial matches

#### 3. Transaction Safety
- **Unique Constraint:** `(txn_id, invoice_id)` prevents double-booking
- **Atomic Operations:** Database transactions ensure all-or-nothing
- **Status Tracking:** No double-approvals possible

#### 4. Comprehensive Audit Trail
- **Append-only Log:** All operations permanently recorded
- **Event Types:** import_bank_transactions, import_invoices, import_conflict, import_row_failed, reconciliation_run, suggestion_approved
- **Full Traceability:** timestamp, actor_id, event_type, metadata, before/after state

#### 5. Error Handling
- **Per-Record Failures:** Invalid CSV rows logged, import continues
- **Detailed Error Messages:** Row number, ID, specific error reason
- **Examples:** Invalid amounts (NOT_A_NUMBER), encoding errors, malformed dates
- **Import Continues:** 95 valid rows import even if 5 rows fail

## Deployment

### Local Development
```bash
# From project root (c:\Work\portfolio\mockdata)
python app.py

# Application runs on http://localhost:8000
# Access Swagger docs at http://localhost:8000/docs
```

### Koyeb Deployment (Production)
1. **Create Supabase PostgreSQL project** at https://supabase.com
2. **Set environment variable in Koyeb:**
   ```
   DATABASE_URL=postgresql://user:password@aws-1-ap-south-1.pooler.supabase.com:6543/postgres
   ```
3. **Procfile already configured:**
   ```
   web: uvicorn app:app --host 0.0.0.0 --port $PORT
   ```
4. **Push to GitHub → Koyeb auto-deploys**
5. **Access at:** `https://your-app.koyeb.app/docs`

### Database
- **Development:** SQLite (automatic, no setup needed)
- **Production:** PostgreSQL via Supabase (recommended)
- **Tables:** Auto-created on first run, no migrations required

## Configuration

### Reconciliation Rules (MVP - Adjustable)
Edit rules in `app.py` (lines ~180-190):
```python
AMOUNT_TOLERANCE = Decimal("0.05")        # ±0.05
DATE_WINDOW_DAYS = 30                     # ±30 days
CONFIDENCE_EXACT_MATCH = Decimal("0.95")  # Exact match
CONFIDENCE_PARTIAL_MATCH = Decimal("0.75") # Partial match
```

### Hardcoded Actor (MVP)
Default approver: `test@mail.com` 
- All approvals tracked with this actor in audit trail
- Can be overridden in request body when needed

## Testing

### Unit & Integration Tests
```bash
# From project root
pytest app.py -v

# Or with coverage
pytest app.py --cov
```

### Manual Testing with cURL

**Step 1: Import bank transactions**
```bash
curl -X POST "http://localhost:8000/imports/bank" \
  -F "file=@bank_transactions.csv"
```

**Step 2: Import invoices**
```bash
curl -X POST "http://localhost:8000/imports/ar" \
  -F "file=@ar_invoices.csv"
```

**Step 3: Run reconciliation**
```bash
curl -X POST "http://localhost:8000/reconcile/suggest" \
  -H "Content-Type: application/json" \
  -d '{"rule_version": "v1"}'
```

**Step 4: View suggestions**
```bash
curl "http://localhost:8000/reconciliation-suggestions?status=pending&page_size=50"
```

**Step 5: Approve suggestions**
```bash
curl -X POST "http://localhost:8000/reconcile/approve" \
  -H "Content-Type: application/json" \
  -d '{"suggestion_ids": [1, 2, 3]}'
```

**Step 6: View audit trail**
```bash
curl "http://localhost:8000/audit?page_size=100"
```

## Future Enhancements

- Customer name similarity matching (fuzzy matching)
- Partial payment handling with multiple transaction matching
- Overpayment and underpayment detection
- FX conversion handling
- Webhook support for external notifications
- User authentication (JWT)
- Rate limiting
- Async task queue (Pub/Sub integration)

## Support & Documentation

- **Quick Troubleshooting:** Check `/audit` endpoint for operation history
- **Complete Documentation:** See [BACKEND_DOCUMENTATION.md](../BACKEND_DOCUMENTATION.md)
  - User workflows and scenarios
  - Complete API reference with examples
  - Database schema details
  - Deployment checklist
  - Troubleshooting guide

## File Structure

```
c:\Work\portfolio\mockdata\
├── app.py                          # Complete FastAPI application (669 lines)
│                                   # Contains all:
│                                   #  - 13 REST endpoints
│                                   #  - 5 SQLAlchemy models
│                                   #  - 8 Pydantic schemas
│                                   #  - Business logic (services)
│
├── requirements.txt                # Python dependencies
├── Procfile                        # Koyeb deployment config
├── .env                            # Environment variables (git-ignored)
├── .gitignore                      # Git ignore rules
├── openapi.json                    # OpenAPI 3.0 specification (auto-generated)
├── reconciliation.db               # SQLite database (development only)
│
├── BACKEND_DOCUMENTATION.md        # Complete technical documentation
│                                   # Includes:
│                                   #  - User flows (4 scenarios)
│                                   #  - Detailed API reference
│                                   #  - Database schema
│                                   #  - Deployment guide
│                                   #  - Troubleshooting
│
└── reconciliation_backend/README.md # This file (quick reference)
```

**Note:** Everything is now in `app.py` (single entry point) for simplicity and ease of deployment.

## Support

For issues or questions, check the audit logs via `/audit` endpoint for detailed operation history.
