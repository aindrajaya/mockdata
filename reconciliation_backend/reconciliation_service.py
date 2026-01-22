"""
Reconciliation engine service
Implements matching logic and suggestion generation
"""
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import and_
from sqlalchemy.orm import Session
from models import BankTransaction, Invoice, ReconciliationSuggestion, ReconciliationEntry, AuditEvent


class ReconciliationService:
    """Service for reconciliation matching and suggestion generation"""
    
    # Configuration for MVP matching rules
    AMOUNT_TOLERANCE = Decimal("0.05")  # ±0.05 for rounding
    DATE_WINDOW_DAYS = 30  # ±30 days
    CONFIDENCE_EXACT_MATCH = Decimal("0.95")
    CONFIDENCE_PARTIAL_MATCH = Decimal("0.75")
    
    @staticmethod
    def run_reconciliation(rule_version: str, db: Session) -> dict:
        """
        Run reconciliation matching rules
        Returns summary of suggestions created, skipped, and unmatched
        """
        created = 0
        skipped = 0
        unmatched_txns = 0
        unmatched_invoices_set = set()
        
        # Load all unmatched transactions (no reconciliation entries)
        unmatched_txns_list = db.query(BankTransaction).filter(
            ~BankTransaction.reconciliation_entries.any()
        ).all()
        
        # Load all open or partially_paid invoices
        open_invoices = db.query(Invoice).filter(
            Invoice.status.in_(["open", "partially_paid"])
        ).all()
        
        unmatched_invoices_set = set(inv.invoice_id for inv in open_invoices)
        
        for txn in unmatched_txns_list:
            # Find candidate invoices
            candidates = ReconciliationService._find_candidates(
                txn, open_invoices
            )
            
            if not candidates:
                unmatched_txns += 1
                # Log unmatched transaction event
                ReconciliationService._audit_unmatched_txn(db, txn.txn_id)
                continue
            
            # Process candidates
            for candidate_inv, confidence, reason in candidates:
                suggestion_key = ReconciliationService._generate_suggestion_key(
                    txn.txn_id, candidate_inv.invoice_id, rule_version
                )
                
                # Check if suggestion already exists (idempotent)
                existing = db.query(ReconciliationSuggestion).filter(
                    ReconciliationSuggestion.suggestion_key == suggestion_key
                ).first()
                
                if existing:
                    skipped += 1
                    continue
                
                # Create new suggestion
                suggestion = ReconciliationSuggestion(
                    suggestion_key=suggestion_key,
                    txn_id=txn.txn_id,
                    invoice_id=candidate_inv.invoice_id,
                    rule_version=rule_version,
                    confidence=confidence,
                    reason=reason,
                    status="pending"
                )
                db.add(suggestion)
                created += 1
                
                # Remove from unmatched invoices if strongly matched
                if confidence >= ReconciliationService.CONFIDENCE_EXACT_MATCH:
                    unmatched_invoices_set.discard(candidate_inv.invoice_id)
        
        db.commit()
        
        # Log reconciliation run completion
        ReconciliationService._audit_reconcile_run(
            db, rule_version, created, unmatched_txns
        )
        
        return {
            "rule_version": rule_version,
            "suggestions_created": created,
            "suggestions_skipped": skipped,
            "unmatched_transactions": unmatched_txns,
            "unmatched_invoices": len(unmatched_invoices_set),
            "timestamp": datetime.utcnow()
        }
    
    @staticmethod
    def _find_candidates(txn: BankTransaction, invoices: list) -> list:
        """
        Find candidate invoices for a bank transaction
        Returns: list of (invoice, confidence, reason) tuples
        
        MVP matching rules:
        1. Currency must match exactly
        2. Amount must be equal or within tolerance
        3. Date must be within configurable window
        """
        candidates = []
        txn_abs_amount = abs(txn.amount)
        
        for invoice in invoices:
            # Rule 1: Currency match
            if invoice.currency != txn.currency:
                continue
            
            # Rule 2: Amount tolerance
            amount_diff = abs(invoice.amount_gross - txn_abs_amount)
            if amount_diff > ReconciliationService.AMOUNT_TOLERANCE:
                continue
            
            # Rule 3: Date window
            date_diff = abs((txn.txn_date - invoice.invoice_date).days)
            if date_diff > ReconciliationService.DATE_WINDOW_DAYS:
                continue
            
            # Determine confidence and reason
            if amount_diff == 0:
                confidence = ReconciliationService.CONFIDENCE_EXACT_MATCH
                reason = "Exact amount and currency match, date within window"
            else:
                confidence = ReconciliationService.CONFIDENCE_PARTIAL_MATCH
                reason = f"Amount within tolerance (diff: {amount_diff}), currency match, date within window"
            
            candidates.append((invoice, confidence, reason))
        
        return candidates
    
    @staticmethod
    def _generate_suggestion_key(txn_id: str, invoice_id: str, rule_version: str) -> str:
        """Generate deterministic suggestion key (idempotency)"""
        key_string = f"{txn_id}-{invoice_id}-{rule_version}"
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    @staticmethod
    def _audit_unmatched_txn(db: Session, txn_id: str):
        """Log unmatched transaction audit event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            actor_type="system",
            actor_id="reconciliation_service",
            event_type="unmatched_transaction",
            entity_type="BankTransaction",
            entity_id=txn_id,
            metadata_json={"reason": "No matching invoice found"}
        )
        db.add(event)
        db.commit()
    
    @staticmethod
    def _audit_reconcile_run(db: Session, rule_version: str, 
                            created: int, unmatched: int):
        """Log reconciliation run completion audit event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            actor_type="system",
            actor_id="reconciliation_service",
            event_type="reconcile_run_completed",
            entity_type=None,
            entity_id=None,
            metadata_json={
                "rule_version": rule_version,
                "suggestions_created": created,
                "unmatched_transactions": unmatched
            }
        )
        db.add(event)
        db.commit()
