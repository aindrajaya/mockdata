<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Ok, and then give me the Next.js frontend architecture that can handle heavy data

A solid architecture here is a Next.js “financial cockpit” optimized for large, filterable tables and fast, safe interactions with the reconciliation API.[^1]

## Overall frontend architecture

- **Tech stack**
    - Next.js (App Router) + TypeScript.
    - TailwindCSS + ShadCN UI for a premium dark cockpit.[^1]
    - TanStack Query (React Query) for data fetching, caching, pagination.
    - Optional Recharts for small summary charts.[^1]
- **High‑level structure**
    - `app/` (App Router)
        - `layout.tsx` – dark theme, shell (sidebar, topbar, toasts).
        - `page.tsx` – dashboard overview (KPIs, small chart, quick links).
        - `bank/` – bank reconciliation table view.
        - `invoices/` – AR invoices table view.
        - `audit/` – audit log timeline.
    - `components/`
        - `data-table/` – reusable heavy table (virtualized, sortable, filterable).
        - `reconciliation/` – row cells, status badges, batch actions bar.
        - `filters/` – date range, customer, status filters.
    - `lib/api/` – typed API client + DTOs.
    - `lib/hooks/` – React Query hooks (`useBankTransactions`, `useInvoices`, `useSuggestions`, `useAuditEvents`).

This makes the cockpit feel cohesive while keeping heavy data logic inside reusable table and hook layers.

## Data‑handling strategy

- **Pagination \& server‑side filters**
    - All heavy lists (`bank`, `invoices`, `audit`, `suggestions`) are fetched with query params: `page`, `pageSize`, `status`, `dateFrom`, `dateTo`, `search`, etc.
    - React Query keys encode filters, so cache is segmented and predictable, e.g. `['bank-transactions', {page, status}]`.
- **Virtualized tables**
    - Use row virtualization (via `@tanstack/react-virtual` or similar) inside a ShadCN table wrapper to support thousands of rows smoothly.
    - Only render visible rows; keep row height fixed for performance.
- **Optimistic UI with server truth**
    - Approvals:
        - Immediately mark selected rows as “approving…” while the API call runs.
        - On success, refetch `bank-transactions`, `invoices`, and `suggestions` queries for consistency.
        - On failure, revert state and show error toast.
    - Never compute balances on the client from scratch; always rely on server‑returned fields (e.g. `invoice_status`, `remaining_amount`) to avoid drift.
- **Error and empty states**
    - Explicit banners for API errors (“Backend unavailable, please retry”) and empty states (“No unmatched transactions for this filter”).
    - For CSV upload errors, show per‑row error counts from backend (`import_row_failed`) as badges, not try to re‑parse CSV on frontend for “truth.”


## Bank reconciliation screen (`/bank`)

**Purpose:** dense table for bank transactions + suggestions + batch approvals.

- **Layout**
    - Topbar:
        - Filters: date range, status (`unmatched`, `pending_suggestion`, `awaiting_approval`, `booked`), customer name search.
        - Buttons: “Run reconciliation” (calls `POST /reconcile/run`), “Upload bank CSV”.
    - Main table:
        - Columns: `txn_date`, `description`, `counterparty_name`, `amount`, `currency`, `suggested_invoice_id`, `confidence`, `status`, actions.
        - Sticky header, fixed height viewport, virtualized rows.
    - Batch actions bar:
        - Appears when rows are selected.
        - Actions: “Approve selected suggestions”, “Mark as exception.”
- **Data flow**
    - `useBankTransactions({ page, filters })`:
        - Calls `GET /bank-transactions` with server‑side pagination and filter params.
        - Response includes `rows`, `total`, `page`, `pageSize`.
    - `useReconciliationSuggestions`:
        - Option 1: suggestions are joined server‑side and included in `bank-transactions` API.
        - Option 2: separate endpoint keyed by `txn_ids[]`, hydrated client‑side. For demo, option 1 is simpler and cleaner.
- **Interactions**
    - Selecting rows with suggestions sets internal selection state (by `suggestion_id`).
    - “Approve selected”:
        - Calls `POST /reconcile/approve` with suggestions array.
        - On success, invalidate `bank-transactions`, `invoices`, `audit-events`.


## Invoices screen (`/invoices`)

**Purpose:** monitor invoice status and remaining balances after reconciliation.

- **Layout**
    - Filters: status (`open`, `partially_paid`, `paid`), customer, currency, date range.
    - Table:
        - Columns: `invoice_id`, `customer_name`, `invoice_date`, `due_date`, `amount_gross`, `currency`, `status`, `remaining_amount`, `last_reconciled_at`.
- **Data flow**
    - `useInvoices({ page, filters })` → `GET /invoices`.
    - Clicking an invoice can open a side drawer:
        - Shows all linked reconciliation entries and bank transactions (via `GET /invoices/{invoice_id}/reconciliation-entries`).

This showcases heavy relational data handling without pushing complex logic to the frontend.

## Audit timeline screen (`/audit`)

**Purpose:** visualize the append‑only audit log and prove immutability.[^1]

- **Layout**
    - Filters:
        - `actor_type` (system/user), `event_type` (`import_*`, `reconcile_*`, etc.), date range.
    - List:
        - Infinite scroll or paginated list of events, grouped by day.
        - Each item shows: timestamp, actor, event type, short summary.
    - Detail drawer:
        - On click, shows JSON diff of `before` vs `after` with syntax highlighting.
- **Data flow**
    - `useAuditEvents({ page, filters })` → `GET /audit`.

This directly matches the job’s emphasis on auditability and traceability.[^1]

## Shared UI and state patterns

- **Global shell**
    - Dark mode, responsive, with:
        - Sidebar: links to Bank, Invoices, Audit.
        - Topbar: current role (CFO / Junior), environment indicator (Demo).
- **Role‑based access (minimal demo)**
    - For demo: a simple `role` toggle stored in local state or mock auth context:
        - `CFO`: can approve in bulk, see all views.
        - `Junior`: read‑only or limited approval.
    - Use React context (`AuthContext`) and per‑route checks to show/disable actions.
    - In the proposal you can phrase it as “stubbed role‑based access, designed to be wired to Firebase Auth as in your stack.”[^1]
- **Type safety**
    - All API responses typed with TypeScript interfaces that mirror backend Pydantic models, e.g. `BankTransactionDTO`, `InvoiceDTO`, `AuditEventDTO`.
    - Use Zod or io‑ts on the client if you want to go extra hard on “never trust the network.”

This architecture clearly demonstrates that you can build a **“premium dark‑mode cockpit in Next.js + ShadCN UI” with complex interactive tables for batch approvals and visualizations** as required by the job post, while handling large datasets efficiently and safely.[^1]

<div align="center">⁂</div>

[^1]: Plutus-Web-or-App-Development.pdf

