# Solar Installation Management System — Specification

Version: 1.0
Status: LOCKED — baseline frozen 2026-10-31
Last updated: 2026-10-31
Owner: Aditya

No requirement, exclusion, business rule or stack choice in this document
changes without an explicit instruction from the owner, recorded in
decisions.md. See section 2.

## 1. Purpose

A unified operational platform for a rooftop solar company that currently
runs on WhatsApp, phone calls and paper registers. It carries a customer
from first enquiry to the twenty-year panel warranty.

Operating scale it must handle:
- 40+ installation projects per month.
- 15+ technicians on site work.
- Residential and small commercial customers.
- On-grid and off-grid systems, 1 kW to 5 kW.
- A continuous stream of service calls against installed systems.

The product covers enquiries, surveys, quotations, orders, payments,
inventory with serial traceability, delivery, installation, warranties,
repairs, subsidy paperwork and management reporting.

This is an operational management application. It is not an electrical
design tool, not a statutory accounting system, and makes no
certification claims about the systems it describes.

## 2. How to use this document

This is the authoritative scope and technical baseline. It fixes the
decisions that are expensive to reverse. It deliberately does not
prescribe screen layouts, component structure, exact form fields, or
internal code organization.

**Fixed here — change only by explicit owner instruction:**
the technology stack, the business workflow and its state machines, the
business rules in section 6 and sections F01–F20, the data that must be
captured for traceability, and the scope exclusions in section 11.

**The builder's call:** UI design and navigation, form layout and
optional fields, module and file organization, naming within the
conventions in rules.md, query and index tuning, test structure, and any
implementation detail that does not change observable behaviour.

Scope governance:
- After baseline approval, features, exclusions, business rules and stack
  choices cannot be added, removed or substituted without the owner's
  explicit instruction.
- Time pressure and implementation difficulty do not authorize dropping
  a requirement. Raise it instead.
- Authorized changes are recorded in decisions.md with their reason.
- Finishing a feature does not authorize expanding it.

Companion documents:
- rules.md — how the team works, team responsibilities, coding standards.
- decisions.md — decision register, open questions, progress, evidence,
  and the subsidy research register.

## 3. Technology baseline

Release families are fixed. Exact patch versions are locked at setup.

| Layer | Selection |
|---|---|
| Backend language | Python 3.12 |
| Backend framework | Django 5.2 LTS |
| API framework | Django REST Framework 3.16 |
| Database | PostgreSQL 16, running locally |
| Database driver | psycopg 3 |
| ORM and migrations | Django ORM, Django migrations |
| Frontend | React 19 with TypeScript 5 |
| Build tool | Vite 7 on Node.js 22 (min 22.12), npm |
| Routing | React Router 7 |
| Server state | TanStack Query 5 |
| Styling | CSS Modules with shared design tokens |
| Authentication | Django sessions, HTTP-only cookies, CSRF protection |
| Charts | Recharts 3 |
| Camera scanning | @zxing/browser 0.1 family |
| Hardware scanning | Keyboard-wedge scanner support |
| Signatures | Browser canvas with Pointer Events |
| PDF generation | ReportLab 4 |
| Image processing | Pillow |
| File storage | Private local filesystem, metadata in PostgreSQL |
| Customer messaging | Telegram Bot API via HTTPX |
| Background work | PostgreSQL outbox plus a Django worker command |
| Deployment | Docker Compose v2, Gunicorn 23, WhiteNoise 6 |
| Tests | Django test runner, DRF test utilities, Playwright |

Runtime layout:
- The browser talks to a same-origin Django API; Vite proxies in dev.
- Deployment serves the built frontend and the API from one origin.
- PostgreSQL holds all business records; a private local volume holds
  uploaded documents and images.
- A worker process handles Telegram delivery and scheduled reminders.
- No external database or hosted backend service is required.

### 3.1 Why SQL, and why PostgreSQL

The core data is densely relational: customers, sites, orders, assets,
deliveries, invoices, payments, assignments and tickets all reference
each other, and the reporting is cross-entity aggregation.

PostgreSQL gives foreign keys and uniqueness constraints, transactions
across related writes, row locking for contested stock and payment
transitions, and reliable aggregation for the director's dashboard.

MongoDB is not chosen because the workload fits relational constraints
and cross-record reporting — a workload-fit judgement, not a claim that
document stores cannot be consistent. SQLite is not chosen as the primary
store because concurrent inventory, payment and scheduling writes matter
here. JSON columns may hold bounded snapshots and external message
payloads; core relationships stay relational.

### 3.2 Why the Django ORM, alone

The ORM handles ordinary reads, writes, relationships and migrations, and
integrates with Django's authentication, admin and validation. The team
still owns query quality: understand the generated SQL, avoid N+1 reads,
use `select_related`/`prefetch_related`, and index against real query
patterns. Keep constraints in the database where the database can express
them.

Parameterized raw SQL is allowed where a query or performance need
justifies it, recorded in decisions.md. No SQLAlchemy alongside Django,
and no extra repository abstraction layer.

### 3.3 Deliberately excluded tooling

Supabase, Firebase and hosted databases; a second primary datastore;
Redis, Celery, Kafka and RabbitMQ; microservices and Kubernetes; GraphQL;
a general-purpose workflow engine; LLM-generated component lists or
pricing; WebSockets. Database-backed jobs and targeted polling cover this
volume. Forty projects a month does not justify distributed
infrastructure.

## 4. Business workflow

```
enquiry → sales follow-up → qualification → site survey → survey approval
→ generated quotation → customer acceptance → order confirmation
→ payment clearance → stock reservation → packing and scan verification
→ dispatch → delivery confirmation (warranty starts)
→ installation and testing → customer acceptance → balance settlement
→ project completion → after-sales support
```

Financial, delivery, installation and support statuses are independent
dimensions. A delivered order is not automatically installed, and an
installed system is not automatically paid for.

## 5. Roles

Administrator, Sales, Operations Manager, Warehouse, Technician, Support,
Finance, Director. One staff member may hold several roles.

The customer is not a system user. They submit the public enquiry form,
sign on a staff-held device under supervision, receive exported
documents, and — once Telegram is implemented — interact through the bot.
There is no customer dashboard.

Permissions per role are defined in rules.md.

## 6. Cross-cutting rules

These apply to every feature. They are not restated per requirement.

**Money.** All amounts are INR, stored as decimals. Never binary floating
point. Every stored amount declares whether it is tax-inclusive or
tax-exclusive. Collections, earned revenue, costs, subsidy estimates and
margin are distinct metrics and are never conflated in a figure or a
label.

**Time.** Timestamps are created by the server and stored in UTC,
displayed in Asia/Kolkata. Business day, week and month boundaries use
Asia/Kolkata; weeks start Monday. The time an event actually happened
(delivery, work start, work finish) is a separate recorded field from the
time it was entered, and both are preserved. Correcting an actual-event
time requires a reason and leaves an audit entry.

**Snapshots.** Issuing a document freezes what it asserts. An issued
quotation keeps its prices, quantities and package version; a warranty
keeps its policy version at delivery. Later catalogue, price or policy
changes never rewrite an issued document or an active coverage record.

**History.** Issued quotations, accepted orders, payments, deliveries,
warranty records and resolved tickets are never hard-deleted. Use
archive, cancellation, reversal and supersession. Corrections create
records; they do not overwrite them.

**Audit.** Every state transition and controlled correction records the
actor, the action, the affected record, the server timestamp, the
relevant before/after values, and the stated reason where one is
required.

**Concurrency.** Stock allocation, dispatch, delivery, payment
allocation and replacement linkage run inside database transactions with
row locks on the contested rows. Critical operations accept an
idempotency key, and generated relationships carry unique constraints, so
a repeated request cannot create a second project, invoice or
reservation. Stale edits are rejected on a revision check rather than
silently overwritten.

**Authority.** Business rules, permissions and all financial calculation
are enforced on the backend. Frontend validation is a convenience only.
Errors name the field or the failed prerequisite.

**Lists.** Search, filter and sort happen on the backend. Page-number
pagination, 25 per page, maximum 100. Ordering is stable with ID as the
tie-breaker. List views persist their filters in the URL and handle
loading, empty, error and permission-denied states. Destructive or
financial transitions confirm before they run.

**Honest labelling.** A drawn signature is in-app evidence of acceptance,
not an Aadhaar eSign or a certified digital signature. A subsidy estimate
is not an approval or a disbursement. The operational margin defined in
F15 is a defined business metric, not statutory accounting profit. A
capacity recommendation is advisory, not a certified electrical design.

## 7. Functional requirements

### F01 — Customers, sites and enquiries

Enquiries arrive from the public web form or are entered by staff from a
phone call or message, always with source attribution. An enquiry is
saved durably before the submitter sees success, returns a reference
number, and lands in the sales queue immediately. If the save fails the
submitter sees an explicit error — enquiries must not vanish.

Must capture: contact details, residential or commercial, site address
with state/UT, requested system type and capacity where known, source,
electricity connection details, monthly consumption in kWh where
available, monthly bill amount with its billing period, an electricity
bill attachment, and estimated shadow-free roof area.

Rules:
- Bill amount and consumption are separate fields. Never derive one from
  the other.
- A customer may have several sites; a site may have several projects.
- A potential duplicate (matching phone or address) is flagged for staff
  review. Never silently discard or merge the incoming enquiry.

Automatic WhatsApp ingestion is excluded. Telegram intake is F16.

### F02 — Qualification and follow-up

Every lead has an owner, a status, a next action with a due date, a
contact history, and — when closed — a qualification outcome with its
reason.

States: `New → Contacting → Qualified → Survey Scheduled`, with `Lost`
reachable from any state and requiring a reason.

Sales checks roof availability, consumption, grid connection suitability,
customer requirements and document completeness before qualifying.

Unassigned leads and overdue follow-ups are visible to managers as a
work queue. A lead cannot sit with no owner and no next action.

### F03 — Survey and approval

A technician visits and records the physical facts a quotation depends
on: roof dimensions and usable area, orientation and tilt, shading
observations, cable route and measured distance, site access notes, grid
connection details, photos, and a recommended system type and capacity.
Off-grid surveys additionally record critical loads and the requested
backup duration.

States: `Draft → Submitted → Approved`, with `Submitted → Changes
Requested → Submitted` and `Submitted → Rejected`.

Rules:
- Only an authorized approver approves a survey.
- No customer-ready quotation exists without an approved survey.
- An approved survey revision is immutable. Later changes create a new
  revision and force review of any quotation built on the old one.

### F04 — Catalogue, packages and component rules

The catalogue holds products and the package templates that turn an
approved survey into a parts list.

Products carry: SKU, category, description, unit of measure, purchase
cost, selling price, tax configuration, tracking method (serialized or
bulk), warranty policy, and the technical attributes that sizing depends
on.

Packages are versioned bills of materials covering the Solar Panel Set,
On-Grid 1–5 kW, Off-Grid 1–5 kW, and the Installation service line, plus
approved repair parts and labour rates.

A complete package covers everything that goes to site, not just the
headline items: panels, inverter, batteries and charge control for
off-grid, mounting structures, AC and DC wiring, connectors, switches and
protection devices, earthing materials, and installation labour.

Rules:
- Component compatibility comes from reviewed package templates. Do not
  assume every inverter needs the same controller, or that a component
  list can be inferred from capacity alone.
- Cable quantity is derived from the surveyed route distance as
  `distance × waste factor + termination buffer`, rounded up to the
  catalogue's stocking unit. The waste factor and the termination buffer
  in metres are named catalogue settings versioned with the package
  template, never constants in code. Defaults are in section 14.
- Battery selection requires the off-grid load and backup-duration
  inputs. It is never inferred from panel capacity.
- Templates, sizing parameters, price lists and allowance rules are
  versioned and maintained by authorized staff.

The equipment descriptions in the original brief are business inputs, not
an engineering bill of materials.

### F05 — Generated quotations

The backend generates the quotation. Sales does not assemble a component
basket by hand.

Generation consumes: the approved survey revision, the approved capacity
and system type, the versioned package template, measured quantities, the
current price list, installation charges, applicable taxes, and the
separately calculated subsidy estimate from F17.

A quotation records its reference and revision, customer and site, the
survey and package versions it was built from, every line with quantity,
unit and price, subtotal, tax and gross payable, the subsidy estimate and
its stated assumptions, payment terms, a validity date, and its creation
and issue timestamps.

States: `Draft → Issued → Accepted`, with `Issued → Rejected / Expired /
Superseded`.

Rules:
- Missing inputs, missing prices or an incompatible package block
  generation with an explanation naming what is missing. Never generate a
  partial quotation silently.
- A revised quotation supersedes the old one and requires fresh
  acceptance. The superseded revision is retained.

### F06 — Acceptance and signatures

Staff present the quotation on a phone or tablet in a restricted view
that shows the customer their document and nothing else — no margins, no
other customers, no staff navigation.

An acceptance record captures explicit acceptance, the customer's name,
the signature image, the server timestamp, the witnessing staff member,
and the exact document revision with a content hash.

Quotation acceptance, installation acceptance (F11) and service
resolution confirmation (F13) are three separate records. None implies
another.

### F07 — Orders, payments and invoices

On acceptance, confirming the order creates exactly one project, one
warehouse requirement, and one installation job awaiting scheduling.

Payment plans are advance or full payment.

Under the advance plan the configured default is 30% of the gross
payable, which Sales may override per quotation within a permitted range.
The accepted terms record the agreed advance as an amount or a
percentage.

The remaining balance falls due on delivery completion, not on
installation acceptance. The balance and its due date stay visible from
order confirmation until settled.

Dispatch gating:
- Advance plan — dispatch requires the agreed advance recorded as
  cleared.
- Full plan — dispatch requires the full agreed amount cleared.
- Dispatch is additionally blocked until stock conditions (F09) are met.

Because the balance is due at delivery, installation acceptance (F11) is
not a payment gate. A customer who refuses to accept the installation has
already been billed in full: the open work and the refusal reason are
tracked under F10 and F11, and any remedy is a reversal or refund under
the rules above, never a withheld balance.

A payment records amount, method, reference, the payment date, the
recorded-at timestamp, the staff member, status, and its allocation
against invoices or the order.

Rules:
- Payments are recorded by authorized staff. No payment gateway and no
  automatic bank reconciliation.
- Over-allocation and duplicate processing of the same payment are
  prevented at the database level.
- Corrections are reversals or refunds, never destructive edits.
- A deposit is not revenue and is not invoiced twice.

Invoices and receipts are generated as PDFs (F19).

### F08 — Purchasing, receiving and inventory

Stock must have an auditable origin, so procurement is in scope at
minimum: suppliers, purchase orders and lines, goods receipts, the
supplier invoice reference and amount, supplier payment status, and the
acquisition cost of each unit received.

Stock state is tracked as on-hand, reserved, available, dispatched,
delivered or installed, and returned or quarantined. Every physical
change writes a stock-movement record. There is no way to change stock
without a movement.

Tracking method by item type:
- **Serialized** — inverters, batteries, charge controllers and panels.
  Each unit gets an internal asset ID, the manufacturer serial number
  where one exists, its product and goods receipt, acquisition cost,
  current location and status, and — after delivery — its customer and
  installation.
- **Bulk** — cable and other consumables are tracked by scanned
  batch/container ID with a quantity and unit. Do not fabricate a
  manufacturer serial number for a length of cable.
- Discrete accessories may be given internal labels where useful.

This is how "scan every item" is implemented honestly: every item is
accounted for and scanned, at the identity its physical form actually
supports.

### F09 — Reservation, packing, scanning and dispatch

Reservation is transactional. Two orders can never hold the same
serialized unit.

The packing checklist comes from the accepted order. Tracked equipment
requires a scan; consumables require a scan of the batch plus a counted
quantity.

The scan step rejects: the wrong product, a unit allocated to another
order, an already-dispatched asset, a repeated scan of the same item, and
any attempt to close packing with required quantities missing.

Scanner support covers USB and Bluetooth keyboard-wedge scanners and
camera-based barcode/QR scanning. A manual fallback exists, is
permission-controlled, and requires a reason that is written to the audit
log.

States: `Pending → Reserved → Packed → Dispatched → Delivered`.

Initial deliveries are complete-order deliveries. A shortage produces a
blocked status and a procurement action rather than a partial dispatch.

Delivery completion records the recipient, the actual delivery timestamp,
proof or staff confirmation, and the exact assets and quantities
delivered. Completing delivery is what activates warranties (F12) — not
packing, not dispatch.

### F10 — Scheduling and installation

Maintain technicians, their availability and their active assignments.
Jobs may be assigned to a team of several technicians.

Schedulable work: surveys, installations and service visits.

Rules:
- Overlapping confirmed assignments for one technician are rejected.
- Rescheduling requires a reason and preserves the previous schedule.
- A technician sees their assigned jobs with the customer and site detail
  the job requires, and no more.
- Installation cannot be completed before the required materials are
  recorded as delivered.

States: `Scheduled → In Progress → Awaiting Customer Acceptance →
Completed`. Delays and blocked work are recorded with an owner and a
reason.

### F11 — Installation evidence and acceptance

The crew completes a form on a phone or tablet at the site. It records
the actual start and finish time, the confirmed system type and installed
capacity, the installed equipment by serial, checklist results, the
power-generation test result, captioned photographs of the finished work,
and notes. The customer then signs on the same screen to accept.

Rules:
- A finish time earlier than the start time is rejected.
- Completion with required evidence missing is rejected.
- Acceptance applies to a specific document revision; accepting a
  different revision than the one presented is rejected.
- A customer who refuses to accept leaves the work open with a recorded
  reason. Refusal is a valid outcome, not an error.

On acceptance the system holds proof of what was installed, and the
customer receives the handover document defined in F19.

### F12 — Warranties

Completing a delivery creates a warranty record for every eligible asset,
automatically. Nobody types dates into a register.

Each record holds the asset, the customer and site, the delivery
timestamp, the policy version, the duration, the coverage start and
expiry, the coverage conditions, and the replacement history.

Rules:
- Coverage is start-inclusive and expiry-exclusive. Calendar arithmetic
  defines its leap-day behaviour explicitly.
- The policy is snapshotted at delivery. Changing a product's policy
  later never rewrites existing coverage.
- A warranty replacement inherits the original's remaining coverage
  unless the policy explicitly grants a fresh period.
- Both the original and the replacement serial are retained and linked.
  The failed unit's history is never overwritten.

Two years for inverters and batteries and twenty years for panels are the
initial configured policies from the brief. They are configuration, not
universal manufacturer terms.

### F13 — Support, diagnosis, repair and replacement

Support finds a customer within seconds by name, phone, project or order
reference, or equipment serial number, and sees that equipment's warranty
status immediately.

A ticket holds the customer and site, the affected assets, the fault
description or code, photos, priority, an assigned owner, status, and the
warranty assessment.

States: `New → Triaged → Visit Scheduled → Diagnosed → Awaiting
Approval/Parts → Work In Progress → Awaiting Customer Confirmation →
Closed`.

Rules:
- A technician visit verifies the fault and records the work
  recommendation before chargeable or covered work proceeds.
- Covered work charges the customer zero for parts and labour, while the
  company's internal parts and labour cost is still recorded against the
  job.
- Non-covered work generates an estimate from configured parts and labour
  rates, requires customer approval before work starts, and invoices from
  the actual approved work. Exceeding approved scope requires fresh
  approval.
- A replacement reserves and issues the new unit, records the old unit as
  returned or quarantined, and links both to the original installation
  and this ticket.
- A ticket closes on recorded customer confirmation, not on the
  technician marking work done. A closed ticket can be reopened with a
  reason.
- Time-based warranty eligibility is judged on the complaint's recorded
  time. Waiting for a technician must never expire an otherwise eligible
  claim. Disputed or backdated cases go to authorized review.

### F14 — Costs, technician hours and finance

Record against each project: equipment consumed, labour hours with the
cost-rate snapshot that applied, direct project expenses, repair costs,
supplier invoices and payments, customer invoices, collections and
refunds, and technician payable and paid records.

Costing:
- A serialized asset carries its recorded acquisition cost.
- Bulk consumables use a documented weighted-average cost.
- Returns reverse the originally allocated cost.

Double-counting rules:
- Buying stock is not a project expense. Cost is allocated to a job when
  stock is issued or consumed.
- Collecting cash is not the same metric as earning revenue.
- A subsidy estimate is never a customer payment.
- Labour cost and labour payment are two views of the same work, not two
  costs.

Technician pay is an accrual ledger, not payroll. A time entry accrues a
payable at the technician's cost rate as it stood when the work was done;
Finance records payments against that accrued balance. This yields labour
cost per job for F15 and an outstanding payable per technician.

Out of scope here: payslips, statutory deductions, tax filing, advances
and adjustments against a technician, full payroll, and a general ledger.

### F15 — Director dashboard and exports

Filters: today, this week, this month, a custom range, project status and
system type. Boundaries use Asia/Kolkata; weeks start Monday.

The dashboard answers the director's actual questions: which jobs made
money, which lost money, and what is unfinished. It shows new and overdue
enquiries, installations completed and outstanding, blocked work,
customer advances and collections, outstanding balances, stock purchases
and supplier payables, technician hours and labour cost, open repairs
split by warranty and non-warranty, and profitable versus loss-making
jobs.

It keeps these four figures visually and semantically distinct: quoted or
projected margin, completed-job operational margin, cash collected, and
cash paid.

Completed-job operational margin is defined as: net job revenue excluding
taxes and reversals, minus allocated equipment cost, minus labour cost,
minus direct job expenses. Warranty service cost incurred later is shown
separately, alongside a lifetime job contribution view that includes it.

Every aggregate card drills down to the records that produced it — a
number the director cannot trace is not trusted.

Exports produce filtered tables as CSV and summaries as PDF, both
stamping the filter period they represent. Exports respect the requesting
user's permissions. There are no anonymous public financial views.

### F16 — Telegram integration (final phase)

Telegram is in scope and is built after the core workflows are working.
It gives the customer a channel without building them a dashboard.

Customer side: link an account using a staff-issued single-use expiring
token, receive relevant status updates, raise a service complaint with
attachments, receive visit updates, and confirm resolution or ask for
more help.

Staff side: receive assigned-ticket notifications, read customer replies
inside the application, and escalate to a person.

Security:
- A chat ID binds to a verified customer record, and the binding is
  revocable.
- Never disclose a record because someone typed a phone number or serial
  into the chat.
- Deduplicate incoming updates; keep tokens and credentials out of logs.

Implementation: long polling for the local deployment; outgoing messages
go through the PostgreSQL outbox with retries, sent after the business
transaction commits. A network outage must never roll back or corrupt the
business action that triggered the message. The bot relays and collects;
it does not autonomously settle financial or technical disputes.

No WhatsApp integration and no AI chatbot.

### F17 — Subsidy estimation and paperwork

A subsidy applies where a rule exists for the site's state and the
customer qualifies. Everywhere else the quotation simply has no subsidy
line and totals normally. There is no placeholder, no warning banner and
no partial estimate.

Schemes are versioned per state/UT. A rule version carries its scheme
name and authority, jurisdiction, eligible customer category and system
type, capacity slabs and caps, any income or category condition,
effective dates, required documents, source URL and last-checked date.

Capital subsidy and per-kWh generation incentive are separate rule
types and are never added into one figure.

Rules:
- A rule either computes an amount or does not exist. Never interpolate
  from a stated range or display a guess.
- A residential scheme does not apply to commercial or off-grid systems
  unless its rule says so.
- An estimate is not an approval and not a disbursement.
- Never subtract an estimated subsidy from the invoice balance unless
  the payment arrangement explicitly works that way.

Active rules at launch are listed in the decisions.md register: central
PM Surya Ghar plus nine state and UT schemes. Adding or amending a rule
is a data change, never a code change.

Application tracking: `Not Started → Documents Pending → Submitted →
Approved → Disbursed`, plus `Rejected` and `Needs Correction`, with
notes, official reference numbers and uploaded paperwork. Submission to
government portals is out of scope.

The quotation shows the subsidy breakdown and the assumptions behind it.

### F18 — Audit, search and reliability

Every record carries server-created creation and update timestamps, and
every state transition and controlled correction writes an audit entry
per the audit rule in section 6.

Global search reaches a customer, project, asset serial or ticket from
one entry point. Serial number lookup is the critical path for F13 and is
indexed accordingly.

Core operations survive an application restart with no data loss. The
database and the uploaded files are backed up together, and a restore is
demonstrated before release.

### F19 — Generated documents

The system produces the customer-facing paperwork, from templates, with
no retyping. Each document is a PDF, is stored against its record, is
regenerable, and carries its reference, revision and generation
timestamp.

Required documents:
- **Quotation** — the issued quotation with its component list, pricing,
  tax, subsidy breakdown, terms and validity.
- **Invoice and payment receipt** — per F07, including the zero-charge
  invoice for warranty-covered work.
- **Installation handover** — what was installed, by serial number, with
  capacity, test result, completion date and the customer's acceptance.
  This is the document that settles "what did I actually get".
- **Warranty certificate** — per installation, listing each covered
  asset's serial, policy, coverage start and expiry.
- **Dashboard export** — per F15.

A document generated from a snapshot reproduces that snapshot, not
current catalogue data.

### F20 — Work queues and notifications

The brief's requirement is that nobody has to phone anyone. Creating the
downstream record is necessary but not sufficient — the people who own
the next step have to see it.

Each role has a work queue showing what is waiting on them: new and
overdue enquiries for sales, surveys awaiting approval for the manager,
orders to pack for the warehouse, today's and this week's jobs for
technicians, open tickets for support, cleared-payment and overdue-balance
items for finance.

In-app notification on the events that hand work between roles: order
confirmed (warehouse and scheduling), survey submitted (approver),
delivery completed (installation crew), ticket assigned, payment cleared,
and follow-up overdue.

Notifications are a view over real record state, never a separate source
of truth, and are generated in the same transaction as the state change
they announce. Customer-facing messaging is F16 only.

## 8. Data model outline

Entities, grouped by area — relationships and exact fields are the
builder's to finalize within the rules above:

- **People** — User, Role, TechnicianProfile.
- **Demand** — Customer, Site, Lead, FollowUp.
- **Survey** — Survey, SurveyRevision, SurveyAttachment.
- **Catalogue** — Product, ProductPrice, PackageTemplate, PackageLine.
- **Sales** — Quote, QuoteLine, Acceptance, SalesOrder, Project.
- **Money** — Invoice, InvoiceLine, Payment, PaymentAllocation, Refund,
  Expense, TechnicianPayment.
- **Supply** — Supplier, PurchaseOrder, GoodsReceipt.
- **Stock** — Asset, StockBatch, StockMovement, Reservation.
- **Fulfilment** — Delivery, DeliveryLine.
- **Field work** — Assignment, InstallationReport, TimeEntry.
- **Warranty** — WarrantyPolicy, AssetWarranty.
- **Service** — ServiceTicket, Diagnosis, RepairOrder, Replacement.
- **Subsidy** — SubsidyScheme, SchemeVersion, SubsidyAssessment,
  SubsidyApplication.
- **Platform** — Attachment, AuditEvent, Notification, Document,
  TelegramBinding, IncomingMessage, OutboxMessage.

Modelling rules:
- Reference customer and site by foreign key. Do not copy mutable
  customer data across tables — except in deliberate document snapshots,
  where the copy is the point.
- An asset stays individually traceable from goods receipt through
  delivery, installation, repair and replacement.
- Payments relate to invoices through allocations, not directly.
- A ticket may concern more than one installed asset.
- Money and measured quantities use decimal types.

## 9. API conventions

REST under `/api/v1/`.

State changes are explicit action endpoints, not field updates: approve
survey, issue quote, accept quote, confirm order, record payment, reserve
stock, dispatch, deliver, complete installation, close ticket. Each one
checks permission, current state, prerequisites and document revision
before acting.

The transaction, idempotency and locking requirements in section 6 apply
to all of them. External calls — Telegram, and anything else over the
network — happen after commit, through the outbox. No network call holds
a stock or payment transaction open.

## 10. Security and file handling

- Role and record-level permissions enforced on the backend. Technicians
  reach their assigned jobs; finance and margin data is restricted;
  customer messaging exposes only the linked customer's records.
- Sessions use CSRF protection and secure cookies under HTTPS. Login and
  the public enquiry endpoint are rate limited.
- Uploads accept PDF, JPEG and PNG with content-type validation, capped
  at 10 MB per file, with image dimension and attachment-count limits in
  named settings.
- Private files live outside any public static directory; downloads are
  authorized per request.
- The database and the file volume are backed up together.
- Never log passwords, session tokens, bot tokens or document contents.

Camera scanning and signature capture on phones require HTTPS. The
deployment plan must include a trusted HTTPS path for phone and tablet
testing on the LAN — the localhost exception does not cover a LAN IP.

## 11. Out of scope

Multi-company SaaS and multi-warehouse routing; a customer dashboard;
WhatsApp; payment gateways and bank reconciliation; a general ledger and
statutory tax filing; full payroll; government subsidy submission APIs;
live generation or IoT telemetry; engineering-grade solar simulation; AI
recommendations or chatbots; offline device sync; partial initial
dispatch; a drag-and-drop workflow designer; native mobile apps.

## 12. Acceptance targets

Proposed test targets, to be measured and recorded, not assumed:

- Seeded with at least 12 months of activity at 40 projects/month, 15+
  active technicians, and installations old enough to exercise warranty
  expiry and service history.
- 25 concurrent active staff sessions.
- Simultaneous ticket creation and contested stock reservation tested
  explicitly.
- p95 under 1 second for ordinary list and detail API requests; under
  2 seconds for dashboard requests. File transfer and PDF generation are
  measured separately.
- Test hardware, dataset size, concurrency and results are recorded.

Forty projects a month is a business volume, not a request rate. The
concurrency targets are what the numbers above actually imply.

## 13. Definition of done

The baseline is complete when:

- Every requirement in section 7 works end to end.
- Permission checks are tested, per role.
- Concurrent allocation cannot double-book a serialized asset.
- A repeated confirmation cannot duplicate a project or an invoice.
- Quotation revisions preserve previously accepted history.
- Payments, balances and allocated costs reconcile.
- Warranty start, expiry and replacement-inheritance rules are tested,
  including the leap-day case.
- A warranty-covered repair invoices the customer zero while its internal
  cost remains visible on the job.
- A ticket cannot close without recorded customer confirmation.
- Every dashboard figure drills down to its source records.
- A Telegram outage leaves core operations uncorrupted.
- Backup and restore are demonstrated.
- Seed data populates a convincing demo of the full lifecycle.
- Documentation describes what was actually built.

A feature is not done because its screen exists.

## 14. Configured defaults

All open decisions were resolved at baseline. The values below are the
agreed starting points. Every one is a named, editable setting — none is
a constant in code, and changing a value is a data change that does not
require a scope change.

| Setting | Default | Governs |
|---|---|---|
| Advance percentage | 30% of gross payable | F07 dispatch gate |
| Advance override range | Sales may set 20–100% | F07 |
| Balance due point | Delivery completion | F07 |
| Quotation validity | 30 days from issue | F05 |
| Cable waste factor | 1.15 × surveyed route distance | F04 |
| Cable termination buffer | 5 m per installation | F04 |
| Inverter / battery warranty | 2 years from delivery | F12 |
| Panel warranty | 20 years from delivery | F12 |
| Upload size limit | 10 MB per file | §10 |
| List page size | 25, maximum 100 | §6 |

Component templates and sizing parameters are authored by the team as
reviewed reference bills of materials — on-grid and off-grid at each
capacity from 1 kW to 5 kW — and reviewed by the owner before a template
version is activated for quotation. An unreviewed template version
cannot produce a customer-facing quotation.

## 15. References

Original requirement: `Solar_Installation_Management_System.pdf`.

Technical: Django 5.2 and DRF documentation, PostgreSQL versioning
policy, Vite guide.

Domain reference: Odoo's solar energy industry package and helpdesk
after-sales documentation, reviewed for workflow comparison only.

Subsidy sources and their verification status are recorded in the subsidy
register in decisions.md. Published policy documents may describe
superseded versions; always check effective dates before activating a
rule.
