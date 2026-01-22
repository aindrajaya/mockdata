"""
FastAPI application for reconciliation service
Exposes REST API for ingestion, reconciliation, and approval workflows
"""
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
import logging

from database import Base, engine, get_db
from models import BankTransaction, Invoice, ReconciliationSuggestion, AuditEvent
from schemas import (
    ImportResponse, ImportError, 
    BankTransactionResponse, InvoiceResponse, ReconciliationSuggestionResponse,
    ApproveRequest, RejectRequest, ReconcileSuggestRequest,
    ApproveResponse, AuditEventResponse, HealthResponse, PaginatedResponse,
    ReconciliationEntryResponse
)
from ingestion_service import IngestionService
from reconciliation_service import ReconciliationService
from approval_service import ApprovalService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Reconciliation Service",
    description="Bank transaction and AR invoice reconciliation engine",
    version="1.0.0"
)

# Create database tables
Base.metadata.create_all(bind=engine)


# ============= Health Check =============
@app.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    try:
        db.execute("SELECT 1")
        database_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        database_status = "disconnected"
        raise HTTPException(status_code=503, detail="Database connection failed")
    
    return HealthResponse(
        status="healthy",
        database=database_status,
        timestamp=datetime.utcnow()
    )


# ============= Import Endpoints =============
@app.post("/imports/bank", response_model=ImportResponse)
def import_bank_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Import bank transactions from CSV file
    
    CSV format expected:
    - txn_id, txn_date, account_iban, counterparty_name, description, amount, currency, bank_reference
    """
    try:
        content = file.file.read().decode('utf-8')
        
        batch_id, imported, skipped, failed, errors = IngestionService.ingest_bank_transactions(
            content, db
        )
        
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
def import_invoices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Import AR invoices from CSV file
    
    CSV format expected:
    - invoice_id, invoice_date, due_date, customer_id, customer_name, amount_gross, currency, status
    """
    try:
        content = file.file.read().decode('utf-8')
        
        batch_id, imported, skipped, failed, errors = IngestionService.ingest_invoices(
            content, db
        )
        
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


# ============= Reconciliation Endpoints =============
@app.post("/reconcile/suggest")
def run_reconciliation(
    request: ReconcileSuggestRequest,
    db: Session = Depends(get_db)
):
    """
    Run reconciliation matching rules and generate suggestions
    
    Returns summary of suggestions created and unmatched items
    """
    try:
        result = ReconciliationService.run_reconciliation(
            request.rule_version, db
        )
        return result
    except Exception as e:
        logger.error(f"Error running reconciliation: {e}")
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {str(e)}")


@app.post("/reconcile/approve", response_model=ApproveResponse)
def approve_suggestions(
    request: ApproveRequest,
    db: Session = Depends(get_db)
):
    """
    Approve and book reconciliation suggestions
    
    Creates reconciliation entries and updates invoice status
    """
    try:
        result = ApprovalService.approve_suggestions(
            request.suggestion_ids,
            request.actor_id,
            db
        )
        
        # Convert entries to response format
        entries = [ReconciliationEntryResponse(**e) for e in result.pop("reconciliation_entries", [])]
        
        return ApproveResponse(
            approved=result["approved"],
            rejected=result["rejected"],
            errors=result["errors"],
            reconciliation_entries=entries,
            timestamp=result["timestamp"]
        )
    except Exception as e:
        logger.error(f"Error approving suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


@app.post("/reconcile/reject")
def reject_suggestions(
    request: RejectRequest,
    db: Session = Depends(get_db)
):
    """
    Reject reconciliation suggestions
    """
    try:
        result = ApprovalService.reject_suggestions(
            request.suggestion_ids,
            request.reason or "User rejection",
            request.actor_id,
            db
        )
        return result
    except Exception as e:
        logger.error(f"Error rejecting suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Rejection failed: {str(e)}")


# ============= Read/Query Endpoints =============
@app.get("/bank-transactions")
def list_bank_transactions(
    status: Optional[str] = Query(None, description="unmatched | matched | all"),
    currency: Optional[str] = Query(None),
    counterparty_name: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("txn_date", description="txn_date | amount | counterparty_name"),
    sort_order: str = Query("asc", description="asc | desc"),
    db: Session = Depends(get_db)
):
    """
    List bank transactions with filtering and pagination
    """
    try:
        query = db.query(BankTransaction)
        
        # Apply filters
        if currency:
            query = query.filter(BankTransaction.currency == currency.upper())
        
        if counterparty_name:
            query = query.filter(
                BankTransaction.counterparty_name.ilike(f"%{counterparty_name}%")
            )
        
        if date_from:
            query = query.filter(BankTransaction.txn_date >= datetime.fromisoformat(date_from))
        
        if date_to:
            query = query.filter(BankTransaction.txn_date <= datetime.fromisoformat(date_to))
        
        # Count total before pagination
        total = query.count()
        
        # Apply sorting
        sort_column = getattr(BankTransaction, sort_by, BankTransaction.txn_date)
        if sort_order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        
        # Apply pagination
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()
        
        # Build response with matched status
        result_items = []
        for txn in items:
            matched_invoices = [
                entry.invoice_id for entry in txn.reconciliation_entries
            ]
            txn_status = "matched" if matched_invoices else "unmatched"
            
            result_items.append({
                "id": txn.id,
                "txn_id": txn.txn_id,
                "txn_date": txn.txn_date,
                "account_iban": txn.account_iban,
                "counterparty_name": txn.counterparty_name,
                "description": txn.description,
                "amount": float(txn.amount),
                "currency": txn.currency,
                "bank_reference": txn.bank_reference,
                "status": txn_status,
                "matched_invoices": matched_invoices,
                "import_batch_id": txn.import_batch_id,
                "created_at": txn.created_at,
                "updated_at": txn.updated_at
            })
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": result_items
        }
    except Exception as e:
        logger.error(f"Error listing bank transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/invoices")
def list_invoices(
    status: Optional[str] = Query(None, description="open | paid | partially_paid | all"),
    currency: Optional[str] = Query(None),
    customer_name: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("invoice_date", description="amount_gross | invoice_date | customer_name"),
    sort_order: str = Query("asc", description="asc | desc"),
    db: Session = Depends(get_db)
):
    """
    List invoices with filtering, pagination, and remaining balance
    """
    try:
        query = db.query(Invoice)
        
        # Apply filters
        if status and status != "all":
            query = query.filter(Invoice.status == status)
        
        if currency:
            query = query.filter(Invoice.currency == currency.upper())
        
        if customer_name:
            query = query.filter(Invoice.customer_name.ilike(f"%{customer_name}%"))
        
        if date_from:
            query = query.filter(Invoice.invoice_date >= datetime.fromisoformat(date_from))
        
        if date_to:
            query = query.filter(Invoice.invoice_date <= datetime.fromisoformat(date_to))
        
        # Count total before pagination
        total = query.count()
        
        # Apply sorting
        sort_column = getattr(Invoice, sort_by, Invoice.invoice_date)
        if sort_order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        
        # Apply pagination
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()
        
        # Build response with matched amounts
        result_items = []
        for inv in items:
            amount_matched = sum(
                Decimal(str(entry.amount_applied)) for entry in inv.reconciliation_entries
            )
            amount_remaining = inv.amount_gross - amount_matched
            matched_txns = [entry.txn_id for entry in inv.reconciliation_entries]
            
            result_items.append({
                "id": inv.id,
                "invoice_id": inv.invoice_id,
                "invoice_date": inv.invoice_date,
                "due_date": inv.due_date,
                "customer_id": inv.customer_id,
                "customer_name": inv.customer_name,
                "amount_gross": float(inv.amount_gross),
                "currency": inv.currency,
                "status": inv.status,
                "amount_matched": float(amount_matched),
                "amount_remaining": float(amount_remaining),
                "matched_transactions": matched_txns,
                "created_at": inv.created_at,
                "updated_at": inv.updated_at
            })
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": result_items
        }
    except Exception as e:
        logger.error(f"Error listing invoices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reconciliation-suggestions")
def list_suggestions(
    status: Optional[str] = Query(None, description="pending | approved | rejected | all"),
    txn_id: Optional[str] = Query(None),
    invoice_id: Optional[str] = Query(None),
    confidence_min: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    List reconciliation suggestions with filtering and pagination
    """
    try:
        query = db.query(ReconciliationSuggestion)
        
        # Apply filters
        if status and status != "all":
            query = query.filter(ReconciliationSuggestion.status == status)
        
        if txn_id:
            query = query.filter(ReconciliationSuggestion.txn_id == txn_id)
        
        if invoice_id:
            query = query.filter(ReconciliationSuggestion.invoice_id == invoice_id)
        
        if confidence_min:
            query = query.filter(ReconciliationSuggestion.confidence >= Decimal(str(confidence_min)))
        
        # Count total
        total = query.count()
        
        # Apply sorting by created_at descending
        query = query.order_by(ReconciliationSuggestion.created_at.desc())
        
        # Apply pagination
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()
        
        result_items = [
            {
                "id": s.id,
                "suggestion_id": s.id,
                "suggestion_key": s.suggestion_key,
                "txn_id": s.txn_id,
                "invoice_id": s.invoice_id,
                "rule_version": s.rule_version,
                "confidence": float(s.confidence),
                "reason": s.reason,
                "status": s.status,
                "created_at": s.created_at
            }
            for s in items
        ]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": result_items
        }
    except Exception as e:
        logger.error(f"Error listing suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit")
def list_audit_events(
    actor_type: Optional[str] = Query(None, description="system | user | all"),
    event_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    List audit events (append-only timeline)
    """
    try:
        query = db.query(AuditEvent)
        
        # Apply filters
        if actor_type and actor_type != "all":
            query = query.filter(AuditEvent.actor_type == actor_type)
        
        if event_type:
            query = query.filter(AuditEvent.event_type == event_type)
        
        if entity_type:
            query = query.filter(AuditEvent.entity_type == entity_type)
        
        if entity_id:
            query = query.filter(AuditEvent.entity_id == entity_id)
        
        if date_from:
            query = query.filter(AuditEvent.timestamp >= datetime.fromisoformat(date_from))
        
        if date_to:
            query = query.filter(AuditEvent.timestamp <= datetime.fromisoformat(date_to))
        
        # Count total
        total = query.count()
        
        # Sort by timestamp descending (most recent first)
        query = query.order_by(AuditEvent.timestamp.desc())
        
        # Apply pagination
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()
        
        result_items = [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "actor_type": e.actor_type,
                "actor_id": e.actor_id,
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "metadata": e.metadata_json,
                "before": e.before_state,
                "after": e.after_state
            }
            for e in items
        ]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": result_items
        }
    except Exception as e:
        logger.error(f"Error listing audit events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": "HTTP_ERROR",
            "timestamp": datetime.utcnow().isoformat()
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
