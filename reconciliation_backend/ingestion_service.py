"""
Ingestion service for bank transactions and invoices
Handles CSV parsing, validation, and idempotent upserts
"""
import csv
import uuid
from io import StringIO
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Tuple
from sqlalchemy.orm import Session
from models import BankTransaction, Invoice, AuditEvent
from schemas import ImportError


class IngestionService:
    """Service for ingesting bank transactions and invoices"""
    
    @staticmethod
    def ingest_bank_transactions(
        file_content: str,
        db: Session
    ) -> Tuple[str, int, int, int, List[ImportError]]:
        """
        Ingest bank transactions from CSV content
        Returns: (batch_id, imported, skipped, failed, errors)
        """
        batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        imported = 0
        skipped = 0
        failed = 0
        errors = []
        
        try:
            reader = csv.DictReader(StringIO(file_content))
            if not reader.fieldnames:
                return batch_id, 0, 0, 0, [ImportError(row=0, error="Empty CSV file")]
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
                try:
                    # Validate required fields
                    txn_id = row.get("txn_id", "").strip()
                    if not txn_id:
                        failed += 1
                        errors.append(ImportError(row=row_num, error="Missing txn_id"))
                        continue
                    
                    # Parse and validate data
                    try:
                        txn_date = datetime.fromisoformat(row.get("txn_date", "").replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        failed += 1
                        errors.append(ImportError(row=row_num, txn_id=txn_id, error="Invalid txn_date format (expected ISO format)"))
                        continue
                    
                    try:
                        amount = Decimal(row.get("amount", "0"))
                    except (InvalidOperation, ValueError):
                        failed += 1
                        errors.append(ImportError(row=row_num, txn_id=txn_id, error=f"Invalid amount: {row.get('amount')}"))
                        continue
                    
                    currency = row.get("currency", "").strip().upper()
                    if not currency or len(currency) != 3:
                        failed += 1
                        errors.append(ImportError(row=row_num, txn_id=txn_id, error="Invalid currency code"))
                        continue
                    
                    account_iban = row.get("account_iban", "").strip()
                    counterparty_name = row.get("counterparty_name", "").strip()
                    description = row.get("description", "").strip()
                    bank_reference = row.get("bank_reference", "").strip()
                    
                    # Check if transaction already exists
                    existing = db.query(BankTransaction).filter(
                        BankTransaction.txn_id == txn_id
                    ).first()
                    
                    if existing:
                        # Check if identical (idempotent)
                        if (existing.amount == amount and 
                            existing.currency == currency and
                            existing.counterparty_name == counterparty_name):
                            skipped += 1
                            continue
                        else:
                            # Conflict: different content with same txn_id
                            failed += 1
                            errors.append(ImportError(row=row_num, txn_id=txn_id, 
                                                    error="Duplicate txn_id with different content"))
                            # Log audit event
                            IngestionService._audit_conflict(
                                db, "BankTransaction", txn_id, 
                                existing.__dict__, 
                                {"amount": amount, "currency": currency, "counterparty_name": counterparty_name}
                            )
                            continue
                    
                    # Create new transaction
                    txn = BankTransaction(
                        txn_id=txn_id,
                        txn_date=txn_date,
                        account_iban=account_iban,
                        counterparty_name=counterparty_name,
                        description=description,
                        amount=amount,
                        currency=currency,
                        bank_reference=bank_reference,
                        import_batch_id=batch_id
                    )
                    db.add(txn)
                    imported += 1
                    
                except Exception as e:
                    failed += 1
                    errors.append(ImportError(row=row_num, error=f"Unexpected error: {str(e)}"))
                    continue
            
            db.commit()
            
            # Log import completion
            IngestionService._audit_import(
                db, "bank", batch_id, imported, skipped, failed
            )
            
        except Exception as e:
            db.rollback()
            errors.append(ImportError(row=0, error=f"CSV parsing error: {str(e)}"))
        
        return batch_id, imported, skipped, failed, errors
    
    @staticmethod
    def ingest_invoices(
        file_content: str,
        db: Session
    ) -> Tuple[str, int, int, int, List[ImportError]]:
        """
        Ingest invoices from CSV content
        Returns: (batch_id, imported, skipped, failed, errors)
        """
        batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        imported = 0
        skipped = 0
        failed = 0
        errors = []
        
        try:
            reader = csv.DictReader(StringIO(file_content))
            if not reader.fieldnames:
                return batch_id, 0, 0, 0, [ImportError(row=0, error="Empty CSV file")]
            
            for row_num, row in enumerate(reader, start=2):
                try:
                    # Validate required fields
                    invoice_id = row.get("invoice_id", "").strip()
                    if not invoice_id:
                        failed += 1
                        errors.append(ImportError(row=row_num, error="Missing invoice_id"))
                        continue
                    
                    # Parse and validate data
                    try:
                        invoice_date = datetime.fromisoformat(row.get("invoice_date", "").replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        failed += 1
                        errors.append(ImportError(row=row_num, invoice_id=invoice_id, error="Invalid invoice_date format"))
                        continue
                    
                    try:
                        due_date = datetime.fromisoformat(row.get("due_date", "").replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        failed += 1
                        errors.append(ImportError(row=row_num, invoice_id=invoice_id, error="Invalid due_date format"))
                        continue
                    
                    try:
                        amount_gross = Decimal(row.get("amount_gross", "0"))
                    except (InvalidOperation, ValueError):
                        failed += 1
                        errors.append(ImportError(row=row_num, invoice_id=invoice_id, 
                                                error=f"Invalid amount_gross: {row.get('amount_gross')}"))
                        continue
                    
                    currency = row.get("currency", "").strip().upper()
                    if not currency or len(currency) != 3:
                        failed += 1
                        errors.append(ImportError(row=row_num, invoice_id=invoice_id, error="Invalid currency code"))
                        continue
                    
                    status = row.get("status", "").strip().lower()
                    if status not in ("open", "paid", "partially_paid"):
                        failed += 1
                        errors.append(ImportError(row=row_num, invoice_id=invoice_id, 
                                                error=f"Invalid status: {status}"))
                        continue
                    
                    customer_id = row.get("customer_id", "").strip()
                    customer_name = row.get("customer_name", "").strip()
                    
                    # Check if invoice already exists
                    existing = db.query(Invoice).filter(
                        Invoice.invoice_id == invoice_id
                    ).first()
                    
                    if existing:
                        # Check if identical (idempotent)
                        if (existing.amount_gross == amount_gross and 
                            existing.currency == currency and
                            existing.status == status):
                            skipped += 1
                            continue
                        else:
                            # Conflict: different content with same invoice_id
                            failed += 1
                            errors.append(ImportError(row=row_num, invoice_id=invoice_id, 
                                                    error="Duplicate invoice_id with different content"))
                            IngestionService._audit_conflict(
                                db, "Invoice", invoice_id,
                                existing.__dict__,
                                {"amount_gross": amount_gross, "currency": currency, "status": status}
                            )
                            continue
                    
                    # Create new invoice
                    invoice = Invoice(
                        invoice_id=invoice_id,
                        invoice_date=invoice_date,
                        due_date=due_date,
                        customer_id=customer_id,
                        customer_name=customer_name,
                        amount_gross=amount_gross,
                        currency=currency,
                        status=status
                    )
                    db.add(invoice)
                    imported += 1
                    
                except Exception as e:
                    failed += 1
                    errors.append(ImportError(row=row_num, error=f"Unexpected error: {str(e)}"))
                    continue
            
            db.commit()
            
            # Log import completion
            IngestionService._audit_import(
                db, "ar", batch_id, imported, skipped, failed
            )
            
        except Exception as e:
            db.rollback()
            errors.append(ImportError(row=0, error=f"CSV parsing error: {str(e)}"))
        
        return batch_id, imported, skipped, failed, errors
    
    @staticmethod
    def _audit_import(db: Session, import_type: str, batch_id: str, 
                     imported: int, skipped: int, failed: int):
        """Log import completion audit event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            actor_type="system",
            actor_id="ingestion_service",
            event_type=f"import_{import_type}_completed",
            entity_type=None,
            entity_id=None,
            metadata_json={
                "import_batch_id": batch_id,
                "imported": imported,
                "skipped": skipped,
                "failed": failed
            }
        )
        db.add(event)
        db.commit()
    
    @staticmethod
    def _audit_conflict(db: Session, entity_type: str, entity_id: str,
                       before: dict, after: dict):
        """Log import conflict audit event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            actor_type="system",
            actor_id="ingestion_service",
            event_type="import_conflict",
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before,
            after_state=after,
            metadata_json={"conflict_type": "duplicate_with_different_content"}
        )
        db.add(event)
        db.commit()
