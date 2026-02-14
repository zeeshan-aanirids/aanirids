# Aanirids Admin -> Frappe Parity Roadmap

## Implementation Rules (Locked)
- Implement only flows that are present and wired in Aanirids admin UI.
- Backend (`backend-v2`) is source of truth for create/update/delete.
- Frappe stores integration state, UX fields, and sync metadata.
- If backend route exists but UI does not use it, keep it out-of-scope unless explicitly requested.

## Scope from Current AANIRIDS UI

### In Scope (wired in UI + API)
- Auth + current-user permissions
- Subscribers + user detail flows
- System Users / Roles / Permissions
- Plans / package accounting / policy rules (`radgroupcheck`, `radgroupreply`)
- NAS + NAS Groups + IP Pools + IP Addresses
- Billing (`invoices`, `payments`, `ledgers`, `gst-invoices`)
- Documents + Notes
- Tickets/complaints
- Logs/Reports pages backed by API

### Out of Scope for now
- OLT management (not wired with real API flow)
- Inventory/TR069 placeholders
- Zone management pieces using old/mismatched endpoints (`operators`)

## Current Frappe Coverage (as-is)

### Implemented
- `Aanirids ISP Settings` + `api_client.py` shared API layer
- `Subscriber` (advanced integration: backend CRUD/actions/documents/sync; parity still pending)
- `Salesperson` (backend CRUD via `/system-users` + sync)
- Sync-enabled master doctypes:
  - `ISP`
  - `Plan`
  - `NAS`
  - `NAS Group`
  - `IP Pool`
  - `IP Address`
- Branch sync customization for ERPNext `Branch`

### Missing / Partial
- No parity module for Roles/Permissions
- No parity module for Policies (`radgroupcheck`, `radgroupreply`)
- No parity module for Billing entities/actions
- No parity module for Notes/Documents standalone pages (outside subscriber child docs)
- No parity module for Tickets
- No API-report module layer for logs/reports
- Plan sync logic needs correction before parity-grade use

## Doctype Strategy

### Reuse via Customization
- `User` (linking/logins where needed)
- `Branch` (already customized with external IDs)
- Existing network/subscriber doctypes where schema already exists

### Keep Existing Doctypes (optimize behavior)
- `Subscriber`, `Subscriber Document`, `Salesperson`, `Plan`, `NAS`, `NAS Group`, `IP Pool`, `IP Address`, `ISP`

### New Doctypes to Create (only when module starts)
- `Policy Check` (radgroupcheck parity)
- `Policy Reply` (radgroupreply parity)
- `Invoice` / `Payment` / `Ledger` integration doctypes (if local representation needed for UI parity)
- `Ticket` integration doctype(s)
- Optional report config doctypes for API-driven reports

## Dependency Order (Execution Plan)

1. **RBAC Foundation**
   - System Users, Roles, Permissions, role-permissions, me/permissions mapping
2. **Network Masters**
   - NAS, NAS Group, IP Pool, IP Address parity hardening
3. **Plans + Policies**
   - packages, package-accounting, radgroupcheck/reply
4. **Subscribers Final Parity**
   - complete remaining subscriber gaps after dependencies above are stable
5. **Billing**
   - invoices, payments, ledgers, gst-invoices
6. **Support + Docs**
   - tickets, notes, documents
7. **Logs/Reports**
   - API-driven reports (no heavy raw log sync into Frappe tables)

## Immediate Next Module
- Start with **RBAC Foundation** (System Users / Roles / Permissions), because most UI routes and actions are permission-gated.

## Working Checklist (to execute one-by-one)
- [ ] Create parity matrix for RBAC screens (`route -> API -> payload -> Frappe method`)
- [ ] Implement RBAC doctypes/controllers
- [ ] Verify against Aanirids UI actions
- [ ] Move to next module only after parity check passes

