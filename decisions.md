# Decisions and Progress

Last updated: 2026-10-31
Specification version: 1.0
Baseline status: LOCKED 2026-10-31
Implementation status: IN PROGRESS. F01 to F04 built; see section 5

## 1. Current state

Done:
- Problem statement and owner feature list reviewed and reconciled.
- Odoo's existing solar capabilities researched for workflow comparison.
- Technical stack chosen and justified.
- Workflow, financial, inventory and warranty edge cases identified.
- Subsidy data captured from the supplied source; 10 rules active,
  6 awaiting an exact slab (section 4).
- spec.md, rules.md and decisions.md written to disk.
- Scope baselined and locked at spec.md v1.0.
- All five open decisions resolved (D024-D028).

Not done:
- F05 to F20.
- Role permissions beyond survey review. Other endpoints only require a login.
- Performance targets in spec.md section 12 have not been measured.
- Six states lack an exact slab and fall back to central-only until
  figures are supplied (section 4).

## 2. Decision register

| ID | Decision | Status | Reason |
|---|---|---|---|
| D001 | Solar Installation Management System as the problem statement | Confirmed | Owner choice |
| D002 | Research and scope before implementation | Confirmed | Owner instruction |
| D003 | Local database, no hosted backend service | Confirmed | Owner instruction and competition preference |
| D004 | Three documents: spec, rules, decisions | Confirmed | Owner instruction |
| D005 | Freeze scope at baseline; changes need explicit instruction | Confirmed | Owner instruction |
| D006 | Telegram in scope, implemented last | Confirmed | Owner choice |
| D007 | WhatsApp excluded | Confirmed | Owner choice |
| D008 | No customer dashboard | Confirmed | Owner choice |
| D009 | PostgreSQL 17 as primary database | Superseded by D029 | Relational integrity, transactions, cross-entity reporting |
| D010 | Django 5.2 with the Django ORM, no second ORM | Confirmed | Integrated framework; avoids redundant abstraction |
| D011 | React 19 and TypeScript frontend | Confirmed | Interactive operational screens |
| D012 | Standalone application, not an Odoo add-on | Confirmed | Open competition; full control of the data model |
| D013 | PostgreSQL outbox and a worker, not Redis/Celery | Confirmed | Durable at this volume without extra infrastructure |
| D014 | Serialized tracking for equipment, batch+quantity for consumables | Confirmed | Tracking must match the item's physical identity |
| D015 | Versioned quotations, packages and warranty policies | Confirmed | Issued documents must not change retroactively |
| D016 | Subsidies as versioned eligibility rules, not one rate per state | Confirmed | Screenshot values are not universal policy |
| D017 | One company, one warehouse | Confirmed | Bounds the baseline |
| D018 | Complete initial dispatch only; no partial fulfilment | Confirmed | Avoids fulfilment scope expansion |
| D019 | Manual payment recording, no gateway | Confirmed | Complete local workflow without external dependency |
| D020 | Warranty replacement inherits remaining coverage unless policy says otherwise | Confirmed | Prevents indefinite coverage extension by replacement |
| D021 | Warranty eligibility judged on complaint time, not visit time | Confirmed | Technician backlog must not expire a valid claim |
| D022 | Generated document set as a named requirement (F19) | Confirmed | Brief requires the customer to have proof of what was installed |
| D023 | Role work queues and in-app notifications as a named requirement (F20) | Confirmed | Brief requires that nobody phones anyone to hand off work |
| D024 | Advance default 30%, overridable 20–100%; balance due on delivery completion | Confirmed | Owner decision 2026-10-31, resolving O01 |
| D025 | Technician pay is an hours × rate accrual ledger with payment records | Confirmed | Owner decision 2026-10-31, resolving O04. Gives labour cost per job without payroll |
| D026 | Activate every subsidy rule whose figures are computable; record each rule's provenance | Confirmed | Owner supplied pmsolar.org.in 2026-10-31, resolving O03. Central is official; state figures are secondary |
| D027 | Cable quantity = distance × waste factor + termination buffer, both configurable | Confirmed | Owner decision 2026-10-31, resolving O05 |
| D028 | Component templates authored by the team, owner-reviewed before activation | Confirmed | Resolves O02. An unreviewed template version cannot produce a customer quotation |
| D029 | PostgreSQL 16 instead of 17 | Confirmed | Owner decision 2026-10-31. 16.13 already running locally; no 17-only feature is used. Post-lock amendment to spec.md section 3 |
| D030 | rules.md stays untracked (.gitignore) | Confirmed | Owner decision 2026-10-31. Must be shared with the other builders out of band |
| D031 | Git repo in the project folder, pushed to GitHub | Confirmed | Owner decision 2026-10-31. Supersedes the earlier deferral. Remote: Crriminson/Solar-Installation-Management-System |
| D032 | Local development setup; no Docker for dev | Confirmed | Owner decision 2026-10-31. Each builder installs PostgreSQL 16 and runs their own database per README. Docker Compose stays in spec.md section 3 as the deployment target only, written if and when we deploy |
| D033 | Node 24 in use against a spec floor of Node 22.12 | Confirmed | Machine has v24.12.0, which clears the stated minimum. No spec change |
| D034 | design.md added as a fourth project document | Confirmed | UI is the builders' call under spec.md section 2. Extends D004 |
| D035 | Staff sign in through the app, with session, login and logout endpoints | Confirmed | Sessions are the spec.md section 3 baseline. Staff previously signed in through Django admin |
| D036 | A Django superuser holds every role | Confirmed | The first account on a new install must be able to use the app |
| D037 | Survey review, not only approval, is limited to operations managers and administrators | Confirmed | Sending back and rejecting are the same decision as approving. rules.md section 4 |
| D038 | An approved survey revision becomes Superseded when a newer one is approved | Confirmed | Builder decision 2026-10-31. spec.md F03 requires revising an approved survey. The approval stands until replaced, so a quotation always has one source |
| D039 | Purchase cost is visible to Finance, Director, Operations Manager and Administrator only | Confirmed | Sales must not see it. rules.md section 4. The operations manager maintains the catalogue, so needs it |
| D040 | Taking a package version live needs an Administrator | Confirmed | Implements the owner review in D028. Operations managers maintain packages but cannot activate them |
| D041 | Labour rates and repair parts are catalogue products | Confirmed | A labour line is a service product with a unit and a dated price, so one price history covers both |
| D044 | Additional feature correction commits permitted without rewriting pushed history | Confirmed | Owner, 2026-10-31: "ye make them its fine", approving the exception for F01–F03, stated feature/owner credits and publication. Existing history is retained; author and committer match per commit |

## 3. Resolved decisions and their consequences

All baseline open decisions are closed. Recorded here because each has a
consequence a builder needs to know.

**D024 — balance due at delivery, not installation.** Installation
acceptance is therefore not a payment gate. A customer who refuses to
accept the installation (F11 permits refusal) has already been billed in
full, so the remedy is a reversal or refund, never a withheld balance.
The open work and the refusal reason stay tracked under F10 and F11.
This is a deliberate trade: better cash position against losing the
final payment as leverage on completion quality.

**D025 — accrual, not payroll.** Labour cost per job depends on a cost
rate existing for every technician before their first time entry. A time
entry with no rate snapshot produces an incomplete job margin in F15.

**D026 — a subsidy applies where a rule exists.** Ten rules are active.
Six states give only a range or an undefined slab, so they fall back to
the central subsidy with no state line, no placeholder and no warning.
Supplying exact figures activates them as data. Never interpolate a
midpoint from a range.

**D027 — cable allowance.** The waste factor and termination buffer are
versioned with the package template, so a reissued quotation reproduces
the quantity its original template version produced.

**D028 — template review gate.** Template versions carry a reviewed
flag. Quotation generation (F05) rejects an unreviewed version, which is
why F05 blocks rather than guesses when inputs are missing.

## 4. Subsidy register

Source: https://pmsolar.org.in/en/solar-subsidy-india/, supplied by the
owner, retrieved 2026-10-31. Central figures are PM Surya Ghar and match
MNRE's published slabs. The state figures come from that one aggregator
page, not from each state's own notification — fine to build on, worth
upgrading later. Each rule stores its own source URL and date, so an
upgrade is a data edit.

Active rules:

| Region | Rule |
|---|---|
| Central | PM Surya Ghar — 1 kW ₹30,000 · 2 kW ₹60,000 · 3 kW+ ₹78,000 cap |
| Delhi | ₹10,000/kW, cap ₹30,000 · plus GBI ₹3/kWh as a separate rule |
| Uttar Pradesh | ₹15,000/kW, cap ₹30,000 |
| Rajasthan | ₹17,000 — Mukhyamantri Nishulk Bijli Yojana beneficiaries |
| West Bengal | ₹5,000/kW, cap ₹15,000; additional ₹15,000 SC/ST |
| Bihar | ₹10,000/kW, cap ₹20,000 |
| Ladakh | ₹20,000/kWp |
| Jammu & Kashmir | ₹3,000/kW |
| Puducherry | ₹10,000/kW, cap ₹30,000 |

Not active — the source gives a range or omits the slab, so no amount is
computable. These states get the central subsidy only until exact
figures are supplied: Haryana (Antyodaya, up to ₹50,000), Chhattisgarh
(₹15,000–30,000), Assam (₹15,000–45,000), Jharkhand (₹15,000/kW,
low-income), Goa (GEDA % of benchmark), and the central NER enhancement.

Every other state and UT gets the central subsidy only.

Corroborating official sources for central, Delhi and UP:
- https://solar.delhi.gov.in/page/central-subsidy
- https://solar.delhi.gov.in/public/assets/solar/delhi_solar_policy_2023_with_amendment.pdf
- https://upneda.org.in/MediaGallery/PANP.pdf
- https://sansad.in/getFile/loksabhaquestions/annex/183/AU353_9QfPAn.pdf?source=pqals

## 5. Feature progress

| Feature | Scope | Status | Evidence |
|---|---|---|---|
| F01 | Customers, sites, enquiries | Verified | Phone and normalized-address duplicate flags; explicit review with reason; both records retained. Billing-period and non-negative input validation; private bill downloads; tested role restrictions. Completion tests plus browser enquiry flow |
| F02 | Qualification and follow-up | Verified | Backend owner/due-date rules, five qualification confirmations and outcome reason, audit timeline, stale-edit rejection and preserved form input. Assignment → Contacting → Qualified verified in browser; success, failure and role tests pass |
| F03 | Survey and approval | Verified | Operations assignment and technician record scoping; Changes Requested now corrects and resubmits the same revision per spec. Prior submissions and corrections retained in audit snapshots. Approved revisions stay immutable. Browser correction/resubmission/approval and concurrency/permission tests pass |
| F04 | Catalogue and packages | In Progress | Products, dated prices, versioned packages, review gate and sizing tested, with screens verified in a browser run. Open: the real reference bills of materials and their owner review (D028). seed_catalogue only loads labelled placeholders |
| F05 | Generated quotations | Not Started | Review gate set (D028) |
| F06 | Acceptance and signatures | Not Started | — |
| F07 | Orders, payments, invoices | Not Started | Terms set (D024) |
| F08 | Purchasing and inventory | Not Started | — |
| F09 | Packing, scanning, dispatch | Not Started | — |
| F10 | Scheduling and installation | Not Started | — |
| F11 | Installation evidence | Not Started | — |
| F12 | Warranties | Not Started | — |
| F13 | Support and replacements | Not Started | — |
| F14 | Costs and finance | Not Started | Scope set (D025) |
| F15 | Dashboard and exports | Not Started | — |
| F16 | Telegram | Not Started | Final phase by D006 |
| F17 | Subsidies and paperwork | Not Started | Launch set (D026) |
| F18 | Audit, search, reliability | Not Started | — |
| F19 | Generated documents | Not Started | — |
| F20 | Work queues and notifications | Not Started | — |

## 6. Scope change log

| # | Change | Instruction | Affects |
|---|---|---|---|
| 1 | PostgreSQL 17 → 16 | Owner, 2026-10-31 | spec.md §3 table. No requirement changes; 16.13 already running, no 17-only feature used |
| 2 | Superseded added to the survey revision states | AtharvK-28, 2026-10-31 | F03 states. Needed to meet F03's rule that later changes create a new revision (D038) |

Each entry records: the owner's instruction, previous behaviour, new
behaviour, affected requirement IDs, and the date.

## 7. Baseline record

| Field | Value |
|---|---|
| Approved specification version | 1.0 |
| Approval date | 2026-10-31 |
| Owner instruction | Baseline the scope as written; it may not be modified without explicit instruction |
| Open decisions at lock | None. O01-O05 resolved as D024-D028 |
| Data work carried past lock | Exact slabs for 6 incomplete schemes (section 4); reference bills of materials for review (D028) |
| Implementation authorization | Given. Feature work under way |
