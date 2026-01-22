"""
Pydantic schemas for request/response validation
"""
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import List, Optional, Any


# ============= Bank Transaction Schemas =============
class BankTransactionCreate(BaseModel):
    """Request schema for creating bank transactions"""
    txn_id: str = Field(..., min_length=1)
    txn_date: datetime
    account_iban: str
    counterparty_name: str
    description: Optional[str] = None
    amount: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    bank_reference: str


class BankTransactionResponse(BaseModel):
    """Response schema for bank transactions"""
    id: int
    txn_id: str
    txn_date: datetime
    account_iban: str
    counterparty_name: str
    description: Optional[str]
    amount: Decimal
    currency: str
    bank_reference: str
    status: str  # matched or unmatched
    matched_invoices: List[str] = []
    import_batch_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============= Invoice Schemas =============
class InvoiceCreate(BaseModel):
    """Request schema for creating invoices"""
    invoice_id: str = Field(..., min_length=1)
    invoice_date: datetime
    due_date: datetime
    customer_id: str
    customer_name: str
    amount_gross: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    status: str = Field(..., pattern="^(open|paid|partially_paid)$")


class InvoiceResponse(BaseModel):
    """Response schema for invoices"""
    id: int
    invoice_id: str
    invoice_date: datetime
    due_date: datetime
    customer_id: str
    customer_name: str
    amount_gross: Decimal
    currency: str
    status: str
    amount_matched: Decimal = Decimal("0.00")
    amount_remaining: Decimal
    matched_transactions: List[str] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============= Reconciliation Schemas =============
class ReconciliationSuggestionResponse(BaseModel):
    """Response schema for reconciliation suggestions"""
    id: int
    suggestion_id: str = Field(..., alias="id")
    suggestion_key: str
    txn_id: str
    invoice_id: str
    rule_version: str
    confidence: Decimal
    reason: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True
        populate_by_name = True


class ReconciliationEntryResponse(BaseModel):
    """Response schema for booked reconciliation entries"""
    id: int
    txn_id: str
    invoice_id: str
    amount_applied: Decimal
    created_at: datetime
    
    class Config:
        from_attributes = True


class ApproveRequest(BaseModel):
    """Request schema for approving suggestions"""
    suggestion_ids: List[int]
    actor_id: Optional[str] = "test@mail.com"


class RejectRequest(BaseModel):
    """Request schema for rejecting suggestions"""
    suggestion_ids: List[int]
    reason: Optional[str] = None
    actor_id: Optional[str] = "test@mail.com"


class ReconcileSuggestRequest(BaseModel):
    """Request schema for running reconciliation"""
    rule_version: str = "v1"


# ============= Import Response Schemas =============
class ImportError(BaseModel):
    """Error details for failed import rows"""
    row: int
    txn_id: Optional[str] = None
    invoice_id: Optional[str] = None
    error: str


class ImportResponse(BaseModel):
    """Response schema for import operations"""
    import_batch_id: str
    total_rows: int
    imported: int
    skipped_duplicates: int
    failed: int
    errors: List[ImportError] = []
    created_at: datetime


# ============= Reconciliation Run Response =============
class ReconcileSuggestionDetail(BaseModel):
    """Detail of a suggested match"""
    invoice_id: str
    amount_gross: Decimal
    customer_name: str
    confidence: Decimal
    reason: str


class ReconcileSuggestResponse(BaseModel):
    """Response schema for reconciliation run"""
    rule_version: str
    suggestions_created: int
    suggestions_skipped: int
    unmatched_transactions: int
    unmatched_invoices: int
    timestamp: datetime
    details: Optional[dict] = None  # Optional detailed suggestion breakdown


class ApproveResponse(BaseModel):
    """Response schema for approval operation"""
    approved: int
    rejected: int
    errors: List[dict] = []
    reconciliation_entries: List[ReconciliationEntryResponse] = []
    timestamp: datetime


# ============= Audit Event Schemas =============
class AuditEventResponse(BaseModel):
    """Response schema for audit events"""
    id: int
    timestamp: datetime
    actor_type: str
    actor_id: str
    event_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    metadata: Optional[dict]
    before: Optional[dict]
    after: Optional[dict]
    
    class Config:
        from_attributes = True


# ============= Pagination Schemas =============
class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper"""
    total: int
    page: int
    page_size: int
    items: List[Any]


# ============= Health Check =============
class HealthResponse(BaseModel):
    """Response schema for health check"""
    status: str
    database: str
    timestamp: datetime
