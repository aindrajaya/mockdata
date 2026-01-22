"""
Integrated FastAPI application combining:
1. Work Orders API (original)
2. Reconciliation Service Backend (new)

Run with: python app.py
Deploy to Koyeb with Procfile
"""
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
import logging
import csv
import hashlib
from io import StringIO
from decimal import InvalidOperation
import uuid

from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, UniqueConstraint, Index, Text, JSON
from pydantic import BaseModel, Field

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# ============= Configuration =============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Work Orders & Reconciliation API",
    description="Combined Work Orders API and Bank Transaction Reconciliation Service",
    version="1.0.0"
)

DATA_PATH = Path(__file__).with_name("workOrders-50k.json")

# ============= Database Setup =============
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./reconciliation.db"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ============= Database Models =============
class BankTransaction(Base):
    """Bank transaction records"""
    __tablename__ = "bank_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    txn_id = Column(String(100), unique=True, index=True, nullable=False)
    txn_date = Column(DateTime, index=True, nullable=False)
    account_iban = Column(String(34), nullable=False)
    counterparty_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, index=True)
    bank_reference = Column(String(255), nullable=False)
    import_batch_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_txn_date_currency", "txn_date", "currency"),
    )


class Invoice(Base):
    """Accounts receivable invoices"""
    __tablename__ = "invoices"
    
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(String(100), unique=True, index=True, nullable=False)
    invoice_date = Column(DateTime, index=True, nullable=False)
    due_date = Column(DateTime, nullable=False)
    customer_id = Column(String(100), nullable=False, index=True)
    customer_name = Column(String(255), nullable=False, index=True)
    amount_gross = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_invoice_date_currency", "invoice_date", "currency"),
    )


class ReconciliationSuggestion(Base):
    """Reconciliation suggestions"""
    __tablename__ = "reconciliation_suggestions"
    
    id = Column(Integer, primary_key=True, index=True)
    suggestion_key = Column(String(255), unique=True, index=True, nullable=False)
    txn_id = Column(String(100), ForeignKey("bank_transactions.txn_id"), nullable=False, index=True)
    invoice_id = Column(String(100), ForeignKey("invoices.invoice_id"), nullable=False, index=True)
    rule_version = Column(String(50), nullable=False)
    confidence = Column(Numeric(5, 2), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_status_created", "status", "created_at"),
    )


class ReconciliationEntry(Base):
    """Booked reconciliation entries"""
    __tablename__ = "reconciliation_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    txn_id = Column(String(100), ForeignKey("bank_transactions.txn_id"), nullable=False, index=True)
    invoice_id = Column(String(100), ForeignKey("invoices.invoice_id"), nullable=False, index=True)
    amount_applied = Column(Numeric(18, 4), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        UniqueConstraint("txn_id", "invoice_id", name="uq_txn_invoice"),
    )


class AuditEvent(Base):
    """Append-only audit log"""
    __tablename__ = "audit_events"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    actor_type = Column(String(20), nullable=False)
    actor_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=True, index=True)
    entity_id = Column(String(255), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    
    __table_args__ = (
        Index("idx_event_type_timestamp", "event_type", "timestamp"),
        Index("idx_entity_timestamp", "entity_type", "entity_id", "timestamp"),
    )


# Create all tables
Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for FastAPI to provide DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============= Pydantic Schemas =============

class ImportResponse(BaseModel):
    """Response for import operations"""
    import_batch_id: str
    total_rows: int
    imported: int
    skipped_duplicates: int
    failed: int
    errors: List[dict] = []
    created_at: datetime


class ReconcileSuggestRequest(BaseModel):
    """Request for reconciliation"""
    rule_version: str = "v1"


class ApproveRequest(BaseModel):
    """Request for approval"""
    suggestion_ids: List[int]
    actor_id: Optional[str] = "test@mail.com"


class RejectRequest(BaseModel):
    """Request for rejection"""
    suggestion_ids: List[int]
    reason: Optional[str] = None
    actor_id: Optional[str] = "test@mail.com"


# ============= Services =============

class IngestionService:
    """Service for CSV ingestion"""
    
    @staticmethod
    def ingest_bank_transactions(file_content: str, db: Session):
        """Ingest bank transactions"""
        batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        imported = 0
        skipped = 0
        failed = 0
        errors = []
        
        reader = csv.DictReader(StringIO(file_content))
        for row_num, row in enumerate(reader, start=2):
            try:
                txn_id = row.get("txn_id", "").strip()
                if not txn_id:
                    failed += 1
                    errors.append({"row": row_num, "error": "Missing txn_id"})
                    continue
                
                txn_date = datetime.fromisoformat(row.get("txn_date", "").replace("Z", "+00:00"))
                amount = Decimal(row.get("amount", "0"))
                currency = row.get("currency", "").strip().upper()
                
                if not currency or len(currency) != 3:
                    failed += 1
                    errors.append({"row": row_num, "txn_id": txn_id, "error": "Invalid currency"})
                    continue
                
                existing = db.query(BankTransaction).filter(BankTransaction.txn_id == txn_id).first()
                if existing:
                    if (existing.amount == amount and existing.currency == currency):
                        skipped += 1
                        continue
                    failed += 1
                    errors.append({"row": row_num, "txn_id": txn_id, "error": "Duplicate with different content"})
                    continue
                
                txn = BankTransaction(
                    txn_id=txn_id,
                    txn_date=txn_date,
                    account_iban=row.get("account_iban", ""),
                    counterparty_name=row.get("counterparty_name", ""),
                    description=row.get("description", ""),
                    amount=amount,
                    currency=currency,
                    bank_reference=row.get("bank_reference", ""),
                    import_batch_id=batch_id
                )
                db.add(txn)
                db.commit()
                imported += 1
                
            except Exception as e:
                db.rollback()
                error_msg = str(e).split('\n')[0] if '\n' in str(e) else str(e)
                failed += 1
                errors.append({"row": row_num, "error": error_msg})
                continue
        
        return batch_id, imported, skipped, failed, errors
    
    @staticmethod
    def ingest_invoices(file_content: str, db: Session):
        """Ingest invoices"""
        batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        imported = 0
        skipped = 0
        failed = 0
        errors = []
        
        reader = csv.DictReader(StringIO(file_content))
        for row_num, row in enumerate(reader, start=2):
            try:
                invoice_id = row.get("invoice_id", "").strip()
                if not invoice_id:
                    failed += 1
                    errors.append({"row": row_num, "error": "Missing invoice_id"})
                    continue
                
                invoice_date = datetime.fromisoformat(row.get("invoice_date", "").replace("Z", "+00:00"))
                due_date = datetime.fromisoformat(row.get("due_date", "").replace("Z", "+00:00"))
                amount_gross = Decimal(row.get("amount_gross", "0"))
                currency = row.get("currency", "").strip().upper()
                status = row.get("status", "").strip().lower()
                
                if status not in ("open", "paid", "partially_paid"):
                    failed += 1
                    errors.append({"row": row_num, "invoice_id": invoice_id, "error": f"Invalid status: {status}"})
                    continue
                
                existing = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
                if existing:
                    if (existing.amount_gross == amount_gross and existing.currency == currency):
                        skipped += 1
                        continue
                    failed += 1
                    errors.append({"row": row_num, "invoice_id": invoice_id, "error": "Duplicate with different content"})
                    continue
                
                invoice = Invoice(
                    invoice_id=invoice_id,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    customer_id=row.get("customer_id", ""),
                    customer_name=row.get("customer_name", ""),
                    amount_gross=amount_gross,
                    currency=currency,
                    status=status
                )
                db.add(invoice)
                db.commit()
                imported += 1
                
            except Exception as e:
                db.rollback()
                error_msg = str(e).split('\n')[0] if '\n' in str(e) else str(e)
                failed += 1
                errors.append({"row": row_num, "error": error_msg})
                continue
        
        return batch_id, imported, skipped, failed, errors


class ReconciliationService:
    """Service for reconciliation matching"""
    
    AMOUNT_TOLERANCE = Decimal("0.05")
    DATE_WINDOW_DAYS = 30
    
    @staticmethod
    def run_reconciliation(rule_version: str, db: Session):
        """Run reconciliation matching"""
        created = 0
        skipped = 0
        
        unmatched_txns_list = db.query(BankTransaction).filter(
            ~BankTransaction.reconciliation_entries.any()
        ).all() if hasattr(BankTransaction, 'reconciliation_entries') else db.query(BankTransaction).all()
        
        open_invoices = db.query(Invoice).filter(
            Invoice.status.in_(["open", "partially_paid"])
        ).all()
        
        for txn in unmatched_txns_list:
            for invoice in open_invoices:
                if invoice.currency != txn.currency:
                    continue
                
                amount_diff = abs(invoice.amount_gross - abs(txn.amount))
                if amount_diff > ReconciliationService.AMOUNT_TOLERANCE:
                    continue
                
                date_diff = abs((txn.txn_date - invoice.invoice_date).days)
                if date_diff > ReconciliationService.DATE_WINDOW_DAYS:
                    continue
                
                suggestion_key = hashlib.sha256(
                    f"{txn.txn_id}-{invoice.invoice_id}-{rule_version}".encode()
                ).hexdigest()
                
                existing = db.query(ReconciliationSuggestion).filter(
                    ReconciliationSuggestion.suggestion_key == suggestion_key
                ).first()
                
                if existing:
                    skipped += 1
                    continue
                
                confidence = Decimal("0.95") if amount_diff == 0 else Decimal("0.75")
                reason = "Exact match" if amount_diff == 0 else f"Amount within tolerance ({amount_diff})"
                
                suggestion = ReconciliationSuggestion(
                    suggestion_key=suggestion_key,
                    txn_id=txn.txn_id,
                    invoice_id=invoice.invoice_id,
                    rule_version=rule_version,
                    confidence=confidence,
                    reason=reason,
                    status="pending"
                )
                db.add(suggestion)
                created += 1
        
        db.commit()
        
        return {
            "rule_version": rule_version,
            "suggestions_created": created,
            "suggestions_skipped": skipped,
            "timestamp": datetime.utcnow()
        }


# ============= Original Work Orders Endpoint =============
@app.get("/workorders")
def list_workorders():
    """Original work orders API"""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Missing data file: {DATA_PATH}")
    return FileResponse(DATA_PATH, media_type="application/json")


# ============= Health Check =============
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected", "timestamp": datetime.utcnow()}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database connection failed")


# ============= Reconciliation Endpoints =============
@app.post("/imports/bank", response_model=ImportResponse)
async def import_bank_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import bank transactions from CSV"""
    try:
        content = await file.read()
        content_str = content.decode('utf-8')
        batch_id, imported, skipped, failed, errors = IngestionService.ingest_bank_transactions(content_str, db)
        
        # Log audit event
        audit = AuditEvent(
            actor_type="system",
            actor_id="csv_import",
            event_type="import_bank_transactions",
            entity_type="bank_transaction",
            entity_id=batch_id,
            metadata_json={
                "batch_id": batch_id,
                "imported": imported,
                "skipped": skipped,
                "failed": failed,
                "filename": file.filename
            }
        )
        db.add(audit)
        db.commit()
        
        return ImportResponse(
            import_batch_id=batch_id,
            total_rows=imported + skipped + failed,
            imported=imported,
            skipped_duplicates=skipped,
            failed=failed,
            errors=errors,
            created_at=datetime.utcnow()
        )
    except Exception as e:
        logger.error(f"Error importing bank transactions: {e}")
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


@app.post("/imports/ar", response_model=ImportResponse)
async def import_invoices(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import AR invoices from CSV"""
    try:
        content = await file.read()
        content_str = content.decode('utf-8')
        batch_id, imported, skipped, failed, errors = IngestionService.ingest_invoices(content_str, db)
        
        # Log audit event
        audit = AuditEvent(
            actor_type="system",
            actor_id="csv_import",
            event_type="import_invoices",
            entity_type="invoice",
            entity_id=batch_id,
            metadata_json={
                "batch_id": batch_id,
                "imported": imported,
                "skipped": skipped,
                "failed": failed,
                "filename": file.filename
            }
        )
        db.add(audit)
        db.commit()
        
        return ImportResponse(
            import_batch_id=batch_id,
            total_rows=imported + skipped + failed,
            imported=imported,
            skipped_duplicates=skipped,
            failed=failed,
            errors=errors,
            created_at=datetime.utcnow()
        )
    except Exception as e:
        logger.error(f"Error importing invoices: {e}")
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


@app.post("/reconcile/suggest")
def run_reconciliation(request: ReconcileSuggestRequest, db: Session = Depends(get_db)):
    """Run reconciliation matching"""
    try:
        result = ReconciliationService.run_reconciliation(request.rule_version, db)
        
        # Log audit event
        audit = AuditEvent(
            actor_type="system",
            actor_id="reconciliation_engine",
            event_type="reconciliation_run",
            entity_type="reconciliation_suggestion",
            metadata_json={
                "rule_version": result['rule_version'],
                "suggestions_created": result['suggestions_created'],
                "suggestions_skipped": result['suggestions_skipped']
            }
        )
        db.add(audit)
        db.commit()
        
        return result
    except Exception as e:
        logger.error(f"Error running reconciliation: {e}")
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {str(e)}")


@app.post("/reconcile/approve")
def approve_suggestions(request: ApproveRequest, db: Session = Depends(get_db)):
    """Approve suggestions"""
    try:
        approved = 0
        for suggestion_id in request.suggestion_ids:
            suggestion = db.query(ReconciliationSuggestion).filter(
                ReconciliationSuggestion.id == suggestion_id
            ).first()
            
            if suggestion and suggestion.status == "pending":
                suggestion.status = "approved"
                
                entry = ReconciliationEntry(
                    txn_id=suggestion.txn_id,
                    invoice_id=suggestion.invoice_id,
                    amount_applied=Decimal("0")
                )
                db.add(entry)
                
                # Log audit event
                audit = AuditEvent(
                    actor_type="user",
                    actor_id="test@mail.com",
                    event_type="suggestion_approved",
                    entity_type="reconciliation_suggestion",
                    entity_id=str(suggestion_id),
                    metadata_json={
                        "suggestion_id": suggestion_id,
                        "txn_id": suggestion.txn_id,
                        "invoice_id": suggestion.invoice_id
                    }
                )
                db.add(audit)
                approved += 1
        
        db.commit()
        return {"approved": approved, "timestamp": datetime.utcnow()}
    except Exception as e:
        db.rollback()
        logger.error(f"Error approving suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bank-transactions")
def list_bank_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List bank transactions"""
    try:
        total = db.query(BankTransaction).count()
        offset = (page - 1) * page_size
        items = db.query(BankTransaction).offset(offset).limit(page_size).all()
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": t.id,
                    "txn_id": t.txn_id,
                    "txn_date": t.txn_date,
                    "amount": float(t.amount),
                    "currency": t.currency,
                    "counterparty_name": t.counterparty_name
                }
                for t in items
            ]
        }
    except Exception as e:
        logger.error(f"Error listing transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/invoices")
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List invoices"""
    try:
        total = db.query(Invoice).count()
        offset = (page - 1) * page_size
        items = db.query(Invoice).offset(offset).limit(page_size).all()
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": i.id,
                    "invoice_id": i.invoice_id,
                    "customer_name": i.customer_name,
                    "amount_gross": float(i.amount_gross),
                    "currency": i.currency,
                    "status": i.status
                }
                for i in items
            ]
        }
    except Exception as e:
        logger.error(f"Error listing invoices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reconciliation-suggestions")
def list_suggestions(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List suggestions"""
    try:
        query = db.query(ReconciliationSuggestion)
        if status:
            query = query.filter(ReconciliationSuggestion.status == status)
        
        total = query.count()
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": s.id,
                    "txn_id": s.txn_id,
                    "invoice_id": s.invoice_id,
                    "confidence": float(s.confidence),
                    "status": s.status,
                    "reason": s.reason
                }
                for s in items
            ]
        }
    except Exception as e:
        logger.error(f"Error listing suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit")
def list_audit_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List audit events (append-only timeline)"""
    try:
        query = db.query(AuditEvent)
        
        if event_type:
            query = query.filter(AuditEvent.event_type == event_type)
        if actor_id:
            query = query.filter(AuditEvent.actor_id == actor_id)
        
        total = query.count()
        offset = (page - 1) * page_size
        items = query.order_by(AuditEvent.timestamp.desc()).offset(offset).limit(page_size).all()
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": e.id,
                    "timestamp": e.timestamp,
                    "actor_type": e.actor_type,
                    "actor_id": e.actor_id,
                    "event_type": e.event_type,
                    "entity_type": e.entity_type,
                    "entity_id": e.entity_id,
                    "metadata_json": e.metadata_json,
                    "before_state": e.before_state,
                    "after_state": e.after_state
                }
                for e in items
            ]
        }
    except Exception as e:
        logger.error(f"Error listing audit events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=False
    )
