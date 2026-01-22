"""
Approval service for reconciliation entries
Handles booking of approved suggestions with transaction safety
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from models import ReconciliationSuggestion, ReconciliationEntry, Invoice, AuditEvent


class ApprovalService:
    """Service for approving and booking reconciliation suggestions"""
    
    @staticmethod
    def approve_suggestions(
        suggestion_ids: list,
        actor_id: str,
        db: Session
    ) -> dict:
        """
        Approve and book reconciliation suggestions
        Returns: summary of approved, rejected, errors
        """
        approved = 0
        rejected = 0
        errors = []
        entries = []
        
        for suggestion_id in suggestion_ids:
            try:
                # Load suggestion
                suggestion = db.query(ReconciliationSuggestion).filter(
                    ReconciliationSuggestion.id == suggestion_id
                ).first()
                
                if not suggestion:
                    rejected += 1
                    errors.append({
                        "suggestion_id": suggestion_id,
                        "error": "Suggestion not found"
                    })
                    continue
                
                # Check suggestion status
                if suggestion.status != "pending":
                    rejected += 1
                    errors.append({
                        "suggestion_id": suggestion_id,
                        "error": f"Suggestion is {suggestion.status}, not pending"
                    })
                    continue
                
                # Load invoice
                invoice = db.query(Invoice).filter(
                    Invoice.invoice_id == suggestion.invoice_id
                ).first()
                
                if not invoice:
                    rejected += 1
                    errors.append({
                        "suggestion_id": suggestion_id,
                        "error": "Invoice not found"
                    })
                    continue
                
                # Check if invoice is already fully paid
                if invoice.status == "paid":
                    rejected += 1
                    errors.append({
                        "suggestion_id": suggestion_id,
                        "error": "Invoice already fully paid"
                    })
                    continue
                
                # Load transaction
                txn = db.query(ReconciliationSuggestion).filter(
                    ReconciliationSuggestion.id == suggestion_id
                ).first().bank_transaction
                
                # Determine amount to apply
                # For MVP: apply the full bank transaction amount (absolute value)
                amount_to_apply = abs(txn.amount)
                
                # Check if this would exceed invoice amount (overpayment case)
                if amount_to_apply > invoice.amount_gross:
                    # Still allow, but mark as overpayment
                    amount_to_apply = invoice.amount_gross
                
                # Store invoice before state for audit
                invoice_before = {
                    "status": invoice.status,
                    "amount_gross": float(invoice.amount_gross)
                }
                
                try:
                    # Create reconciliation entry (will fail if already exists due to unique constraint)
                    entry = ReconciliationEntry(
                        txn_id=suggestion.txn_id,
                        invoice_id=suggestion.invoice_id,
                        amount_applied=amount_to_apply
                    )
                    db.add(entry)
                    
                    # Update invoice status
                    invoice.status = "paid"
                    
                    # Update suggestion status
                    suggestion.status = "approved"
                    
                    db.flush()  # Flush to catch unique constraint violations
                    db.commit()
                    
                    # Create audit event
                    ApprovalService._audit_approval(
                        db, actor_id, suggestion.txn_id, 
                        suggestion.invoice_id, amount_to_apply,
                        invoice_before,
                        {
                            "status": "paid",
                            "amount_gross": float(invoice.amount_gross)
                        }
                    )
                    
                    approved += 1
                    entries.append({
                        "id": entry.id,
                        "txn_id": entry.txn_id,
                        "invoice_id": entry.invoice_id,
                        "amount_applied": float(entry.amount_applied),
                        "created_at": entry.created_at.isoformat()
                    })
                    
                except IntegrityError as e:
                    db.rollback()
                    rejected += 1
                    if "uq_txn_invoice" in str(e):
                        errors.append({
                            "suggestion_id": suggestion_id,
                            "error": "This transaction-invoice pair is already booked"
                        })
                    else:
                        errors.append({
                            "suggestion_id": suggestion_id,
                            "error": f"Database constraint violation: {str(e)}"
                        })
                    continue
                    
            except Exception as e:
                db.rollback()
                rejected += 1
                errors.append({
                    "suggestion_id": suggestion_id,
                    "error": f"Unexpected error: {str(e)}"
                })
                continue
        
        return {
            "approved": approved,
            "rejected": rejected,
            "errors": errors,
            "reconciliation_entries": entries,
            "timestamp": datetime.utcnow()
        }
    
    @staticmethod
    def reject_suggestions(
        suggestion_ids: list,
        reason: str,
        actor_id: str,
        db: Session
    ) -> dict:
        """
        Reject reconciliation suggestions
        Returns: summary of rejected
        """
        rejected = 0
        errors = []
        
        for suggestion_id in suggestion_ids:
            try:
                suggestion = db.query(ReconciliationSuggestion).filter(
                    ReconciliationSuggestion.id == suggestion_id
                ).first()
                
                if not suggestion:
                    errors.append({
                        "suggestion_id": suggestion_id,
                        "error": "Suggestion not found"
                    })
                    continue
                
                if suggestion.status != "pending":
                    errors.append({
                        "suggestion_id": suggestion_id,
                        "error": f"Cannot reject {suggestion.status} suggestion"
                    })
                    continue
                
                suggestion.status = "rejected"
                db.commit()
                
                # Create audit event
                ApprovalService._audit_rejection(
                    db, actor_id, suggestion.txn_id,
                    suggestion.invoice_id, reason
                )
                
                rejected += 1
                
            except Exception as e:
                db.rollback()
                errors.append({
                    "suggestion_id": suggestion_id,
                    "error": f"Unexpected error: {str(e)}"
                })
                continue
        
        return {
            "rejected": rejected,
            "errors": errors,
            "timestamp": datetime.utcnow()
        }
    
    @staticmethod
    def _audit_approval(db: Session, actor_id: str, txn_id: str,
                       invoice_id: str, amount: Decimal, before: dict, after: dict):
        """Log approval audit event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            actor_type="user",
            actor_id=actor_id,
            event_type="reconcile_approved",
            entity_type="Invoice",
            entity_id=invoice_id,
            metadata_json={
                "txn_id": txn_id,
                "amount_applied": float(amount)
            },
            before_state=before,
            after_state=after
        )
        db.add(event)
        db.commit()
    
    @staticmethod
    def _audit_rejection(db: Session, actor_id: str, txn_id: str,
                        invoice_id: str, reason: str):
        """Log rejection audit event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            actor_type="user",
            actor_id=actor_id,
            event_type="reconcile_rejected",
            entity_type="ReconciliationSuggestion",
            entity_id=f"{txn_id}-{invoice_id}",
            metadata_json={
                "reason": reason
            }
        )
        db.add(event)
        db.commit()
