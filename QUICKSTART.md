# Reconciliation Service - Quick Reference

## 🚀 Quick Start (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run server
python reconciliation_backend/main.py

# 3. Access
# Swagger UI: http://localhost:8000/docs
# API Base: http://localhost:8000
```

## 🚀 Deploy to Koyeb

```bash
# 1. Create Supabase PostgreSQL project
# 2. Get connection string: postgresql://user:pass@host:port/db
# 3. In Koyeb, set environment variable:
DATABASE_URL=postgresql://...

# 4. Push to GitHub (Procfile already configured)
# 5. Koyeb auto-deploys
# 6. Access at: https://your-app.koyeb.app/docs
```

## 📊 API Endpoints (10 total)

### Import (2)
- `POST /imports/bank` - Upload bank transactions CSV
- `POST /imports/ar` - Upload AR invoices CSV

### Reconciliation (3)
- `POST /reconcile/suggest` - Run matching engine
- `POST /reconcile/approve` - Book approved matches
- `POST /reconcile/reject` - Reject suggestions

### Query (4)
- `GET /bank-transactions` - List bank transactions
- `GET /invoices` - List invoices
- `GET /reconciliation-suggestions` - List suggestions
- `GET /audit` - Audit trail

### Health (1)
- `GET /health` - Health check

## 🔧 Configuration

### Matching Rules (Edit reconciliation_service.py)
```python
AMOUNT_TOLERANCE = 0.05        # ±0.05
DATE_WINDOW_DAYS = 30          # ±30 days
CONFIDENCE_EXACT = 0.95        # Exact match
CONFIDENCE_PARTIAL = 0.75      # Partial match
```

### Default User
```python
actor_id = "test@mail.com"  # Hardcoded for MVP
```

## 📁 Project Structure

```
reconciliation_backend/
├── main.py                  # FastAPI app
├── models.py                # 5 SQLAlchemy models
├── schemas.py               # Pydantic DTOs
├── ingestion_service.py     # CSV parsing
├── reconciliation_service.py # Matching engine
├── approval_service.py      # Approval workflow
├── database.py              # DB config
├── test_main.py             # Test suite
├── generate_openapi.py      # OpenAPI generator
├── README.md                # Full documentation
└── __init__.py
```

## 📋 Features

✅ Idempotent ingestion (no duplicates on re-upload)
✅ Deterministic reconciliation (same results every run)
✅ Transaction safety (prevents double-booking)
✅ Append-only audit trail (full traceability)
✅ Error resilience (continues despite bad rows)
✅ Multi-currency support (DKK, EUR, etc.)
✅ Decimal precision (18,4 for money)
✅ Comprehensive logging (import, reconcile, approve)
✅ OpenAPI 3.0 docs (automatic)
✅ Hardcoded test user (test@mail.com)

## 📊 Data Models

### BankTransaction
```json
{
  "txn_id": "BNK-2026-000001",
  "txn_date": "2026-01-02",
  "account_iban": "DK5000400440116243",
  "counterparty_name": "Acme A/S",
  "description": "Invoice INV-2026-0001 payment",
  "amount": "-2500.00",
  "currency": "DKK",
  "bank_reference": "REF-ACME-0001"
}
```

### Invoice
```json
{
  "invoice_id": "INV-2026-0001",
  "invoice_date": "2025-12-28",
  "due_date": "2026-01-05",
  "customer_id": "CUST-ACME",
  "customer_name": "Acme A/S",
  "amount_gross": "2500.00",
  "currency": "DKK",
  "status": "open"
}
```

## 🧪 Test Data Handling

All edge cases in provided CSVs are handled:

| Case | Result |
|------|--------|
| Exact match | ✅ Confidence 0.95 |
| Rounding (1499.995 → 1500) | ✅ Within tolerance |
| Partial payments | ✅ Multiple suggestions |
| Currency mismatch | ✅ Skipped |
| Invalid amount | ✅ Logged as failed |
| Duplicate txn_id | ✅ Logged as conflict |
| Encoding error | ✅ Logged as failed |
| Unmatched txn | ✅ Logged as unmatched |
| Foreign exchange residual | ✅ Within tolerance |

## 📚 API Examples

### Import Bank Transactions
```bash
curl -X POST http://localhost:8000/imports/bank \
  -F "file=@bank_transactions.csv"
```

### Run Reconciliation
```bash
curl -X POST http://localhost:8000/reconcile/suggest \
  -H "Content-Type: application/json" \
  -d '{"rule_version": "v1"}'
```

### Approve Suggestions
```bash
curl -X POST http://localhost:8000/reconcile/approve \
  -H "Content-Type: application/json" \
  -d '{"suggestion_ids": [1, 2], "actor_id": "test@mail.com"}'
```

### List Suggestions
```bash
curl "http://localhost:8000/reconciliation-suggestions?status=pending"
```

### View Audit Log
```bash
curl "http://localhost:8000/audit?event_type=reconcile_approved"
```

## 🔐 Security Notes

- **Hardcoded user** (`test@mail.com`) for MVP testing
- **No authentication** - add JWT before production
- **No rate limiting** - add before production
- **SQL injection safe** - SQLAlchemy parameterized queries
- **Decimal precision** - safe money handling (18,4)

## 📖 Documentation

- **Swagger UI:** `GET /docs` - Interactive API explorer
- **ReDoc:** `GET /redoc` - Alternative API docs
- **OpenAPI JSON:** `GET /openapi.json` - Machine-readable spec (31 KB)
- **README:** `reconciliation_backend/README.md` - Full guide
- **IMPLEMENTATION_GUIDE:** `IMPLEMENTATION_GUIDE.md` - Detailed overview

## 🐛 Troubleshooting

### Database Issues
```bash
# SQLite only - delete DB and restart
rm reconciliation.db
python reconciliation_backend/main.py
```

### CSV Import Fails
- Check CSV format matches schema
- Check for non-UTF-8 encoding
- Check for numeric values in amount fields

### No Suggestions Created
- Verify `status=open` invoices exist
- Check currency matches (case-sensitive)
- Check date window (±30 days)
- Check amount tolerance (±0.05)

### Need to Delete Data
```bash
# For development/testing only
rm reconciliation.db  # SQLite
# Or reset PostgreSQL tables
```

## 🎯 Next Steps

1. **Local Testing**
   - Import CSVs from `case/reconciliation/`
   - Run reconciliation
   - Approve suggestions
   - Check audit log

2. **Deploy to Koyeb**
   - Create Supabase PostgreSQL
   - Set DATABASE_URL
   - Push code
   - Test endpoints

3. **Frontend Integration**
   - Generate TypeScript client from `/openapi.json`
   - Implement UI for CSV upload
   - Implement suggestion approval interface
   - Add audit log viewer

4. **Production Hardening**
   - Add authentication (JWT)
   - Add rate limiting
   - Set up monitoring
   - Configure backups
   - Add error tracking (Sentry)

## 📝 Key Files

| File | Purpose |
|------|---------|
| `reconciliation_backend/main.py` | FastAPI app (13 endpoints) |
| `reconciliation_backend/models.py` | 5 SQLAlchemy models |
| `reconciliation_backend/ingestion_service.py` | CSV parsing with validation |
| `reconciliation_backend/reconciliation_service.py` | Matching engine |
| `reconciliation_backend/approval_service.py` | Approval workflow |
| `openapi.json` | API specification (31 KB) |
| `IMPLEMENTATION_GUIDE.md` | Detailed guide |
| `requirements.txt` | Python dependencies |
| `Procfile` | Koyeb deployment config |

## ✨ Summary

- **Language:** Python 3.8+
- **Framework:** FastAPI
- **Database:** PostgreSQL (Supabase recommended) or SQLite
- **Deployment:** Koyeb with environment variable
- **Time to deploy:** < 5 minutes
- **Testing:** Handles all provided edge cases
- **Documentation:** Auto-generated OpenAPI specs
- **Status:** Production-ready for MVP use
