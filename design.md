# Solar Installation Management System — UI/UX Design Specification

Version: 2.0
Date: 2026-11-01
Companion to: `spec.md` v1.0 (LOCKED, baseline 2026-10-31)
Status: Current. Describes what is built and the direction for what is not.

**Authority.** `spec.md` wins on any conflict. This document covers only what
spec §2 leaves to the builder: UI design, navigation, form layout, and frontend
module and file organisation. It adds, removes or changes no requirement,
business rule, state machine, exclusion or stack choice. Anything here that
looks like a new requirement is a presentation of an existing one; anything
needing an owner decision is in §19 rather than decided here.

**What changed in 2.0.** Version 1.0-draft was written before `rules.md` and
`decisions.md` were available and before the screens existed, so it specified a
palette, a component inventory and a route map that the code never used. This
version is written from the code. Where 1.0 and the build disagreed, the build
won unless the build was wrong. The visual direction is new: see §4.

Companion documents: `spec.md` (scope), `rules.md` (practices, permissions,
coding standards), `decisions.md` (decisions, progress, evidence).

---

## 1. The idea

**Every screen answers two questions: what is waiting on me, and what happens
next?**

The company runs on WhatsApp, calls and paper registers because that is how
work gets passed along. The brief's test is that nobody has to phone anyone
(F20). So the design is built around handoffs, not modules. A person opens the
app and sees their work. A record shows who holds it now and what it is waiting
for.

Four rules follow:

1. **Work comes first.** The home screen is a work queue, not a chart page.
2. **Every number opens its records.** A count you cannot click is not shown.
3. **State is visible at a glance.** Status never relies on colour alone.
4. **The device fits the job.** Sales and finance sit at desks. Technicians
   stand on roofs. Warehouse staff hold a scanner. They do not get the same
   screen squeezed to fit.

### The balance we want

| | Too lame | Where we aim | Too much |
|---|---|---|---|
| Overall | Django admin with a logo | A sharp work tool, like a well-kept register | A marketing page with a login |
| Colour | Grey everywhere | Structural navy, one blue for action, colour only for status | Gradients and colour-coded everything |
| Density | Giant cards, little data | 40px table rows, comfortable to scan | Spreadsheet walls at 12px |
| Type | One size for everything | A clear scale, tabular numbers, mono references | Display fonts and tracked capitals |
| Motion | None, so changes feel abrupt | 90/160/240ms, tied to what moved and why | Page transitions, parallax, shimmer |

### Principles carried from v1.0

1. **Status is never one dimension.** Financial, delivery, installation and
   support status are independent (spec §4). A project view shows them side by
   side, never merged into one "status".
2. **The backend decides; the UI explains.** Business rules, permissions and
   all money arithmetic live on the server (spec §6). The browser formats and
   presents; it performs no arithmetic on money or quantities.
3. **Blocked means "here is what is missing".** A refused action names the
   field or the failed prerequisite, never a generic error.
4. **Honest labels.** Drawn signature = in-app evidence, not an Aadhaar eSign.
   Subsidy = estimate, not approval. Margin = the F15 operational metric, not
   accounting profit. Capacity = advisory. These strings are requirements from
   spec §6, not optional copy.
5. **History is visible.** Corrections, supersessions, reversals and
   replacements appear as linked records in a timeline, not as edits.
6. **Field work is first-class.** Surveys, installation, scanning and signing
   run on phones over HTTPS, designed mobile-first.
7. **No decorative scope.** Finishing a screen does not authorise adding to it.

---

## 2. Reference study: Kanakku admin template

### 2.1 What was studied, and how far

Source: `https://kanakku.dreamstechnologies.com/html/index.html` (Kanakku
v2.1.8, a commercial invoicing and accounting admin template; its own metadata
advertises it for sale).

| Coverage | Pages |
|---|---|
| Opened and read | `index.html` (dashboard), `quotations.html` (list), `add-quotation.html` (document form), `ticket-kanban.html` (board) |
| Classified from the shared navigation tree | the remaining ~250 destinations across 12 sidebar groups |
| Relevant but not opened — reconcile when built | `customer-details`, `invoice-details`, `calendar`, `roles-permissions`, `inventory`, `esignatures`, `barcode-settings`, `audit-log`, `notifications` |

Every page in the template repeats the same shell, and the four opened pages are
the four archetypes that carry nearly all ERP screens: dashboard, filterable
list, document form, status board.

**Limits, re-checked 2026-11-01.** The page still returns text only; its
stylesheet is not retrievable. **No colour, font, spacing or radius value in
this document comes from Kanakku.** Structure and interaction patterns only.
Kanakku is a paid template: do not copy its markup, CSS, JavaScript, icons or
images. Everything is re-implemented in React and CSS Modules.

### 2.2 Patterns taken

| Area | Observed | Taken as |
|---|---|---|
| Shell | Collapsible left sidebar grouped by section; top header with breadcrumb and profile menu showing the role label | `AppShell`: sidebar groups per module, icon rail, header with breadcrumbs and account menu (§5) |
| Page header | Title left; right-aligned export and one primary button | `PageHeader` with title, status, subtitle and actions |
| Lists | Filter controls, status badge, pagination, row click through | `DataTable` + `FilterTabs` + `SearchInput`, filters in the URL (spec §6) |
| Stat cards | Label, value, a delta or sub-line, and a link to the owning page | Dashboard tiles that state their record count and drill down (§4.6) |
| Document form | Sectioned cards, totals block, signature, sticky footer | Quotation record, installation report, goods receipt |
| Number format | Indian digit grouping (`1,20,500`) | `en-IN` formatting with `₹` (§11) |

### 2.3 Where the template contradicts the spec

A straight copy would break a locked rule in each of these cases.

| Template behaviour | Spec rule it breaks | Our response |
|---|---|---|
| Row delete on quotations, tickets, invoices | §6 History: issued quotations, orders, payments, deliveries, warranties and resolved tickets are never hard-deleted | No delete on those records. Archive, cancel, reverse, supersede, each with a reason |
| Kanban drag to change status; a free Status picker | §9: state changes are explicit action endpoints checking prerequisites | Transitions only through action buttons on the record |
| Quotation form where the user picks products and rates | F05: the backend generates; Sales does not assemble a basket | "Generate from approved survey" plus a read-only result |
| Currency picker, multi-language, RTL | INR and Asia/Kolkata are fixed | Not built |
| Quotation statuses "Sent" / "Declined" | F05 states are Draft, Issued, Accepted, Rejected, Expired, Superseded | The spec's names only |
| Notification with inline Approve / Deny | F03/F07: approvals check permission, state and document revision | Notifications deep-link to the record; no state change from a bell |
| "Total Revenue", "Profit Margin 57.4%" and "Cash Flow" shown together | §6 Money, F15: collections, revenue, cost and margin are distinct and never conflated | Four separately captioned figures with their own identities (§4.6) |
| Revenue target and "% achieved" | No target exists in the spec | Not built. Inventing one would be fake precision |
| Customer dashboard, register, super admin, SaaS billing | spec §5, §11 | Not built |

---

## 3. What is built

F01–F15 are implemented; F16–F20 are not. See `decisions.md` §5 for the
authoritative status and evidence. This table says which archetype each feature
uses, so a new screen starts from a known shape.

| Feature | Archetype | Built |
|---|---|---|
| F01 Enquiries | Public form, List, Side panel | Yes |
| F02 Follow-up | List, Side panel, My work | Yes |
| F03 Survey | Step form (phone), List, Record | Yes |
| F04 Catalogue | List, Record | Yes |
| F05 Quotations | List, Record | Yes |
| F06 Acceptance | Customer view | Supervised path only; remote path is F16 |
| F07 Orders and payments | List, Record, confirm dialogs | Yes |
| F08 Inventory | List, Record | Yes |
| F09 Packing and dispatch | List, Scan station | Yes |
| F10 Scheduling | List, Record, My work | Yes |
| F11 Installation | Step form, Customer view | Yes |
| F12 Warranties | List, Record, order section | Yes |
| F13 Support | List, Record | Yes |
| F14 Costs | Record sections, List | Yes |
| F15 Dashboard | Dashboard, drill-down List | Yes |
| F16 Telegram | Record activity, List | No |
| F17 Subsidies | Quotation section; application List | Estimator only |
| F18 Search and audit | Global search, Record activity | Timeline only |
| F19 Documents | A Documents section on each Record | No |
| F20 Queues | My work, notification list | My work exists; notifications do not |

Two things 1.0 assumed that are not true, and are not planned here: there is no
`FilterDrawer` (lists use `FilterTabs` plus a search box, which fits the number
of filters each list actually has), and there is no ticket board — F13 ships as
a list and a record, which is what D048's four states need.

---

## 4. Design system

CSS Modules over shared tokens in `frontend/src/styles/tokens.css`. No
Bootstrap, Tailwind or component kit. **Screens never write a raw colour, font
size, duration or radius.** Every value comes from a token; `tokens.css` is the
one file that changes how the app looks.

### 4.1 Colour

Structural navy with a single blue for action. The reasoning: this is a dense
operational tool read for hours at a time, and a cool neutral keeps six status
tones legible against it. Warm neutrals with an orange primary — the v1.0 build
— made the status tones compete with the brand.

The logo keeps the solar motif in `--color-mark` and `--color-on-mark`. A brand
mark is identity, not a status colour, so it does not follow the palette.

- **Ink** (`--color-ink`, slate 900) is the dark structural surface: sidebar,
  brand panel. The public form and login carry a solar-array pattern on it,
  which is the app's identity.
- **Blue is for action only:** primary buttons, links, focus rings, the current
  place in navigation, and a drill-down link. One primary button per view area.
- **Status colour is never brand colour.** The six tones in §4.4 are their own
  scale and are used for nothing else.
- **The page is tinted and cards are white.** A white card on a slate page
  lifts without needing a heavy shadow, which is what keeps a dense screen
  calm. The neutral ramp is Tailwind's slate, taken from the palette search
  rather than mixed by hand; bespoke values would be a cosmetic change, not a
  functional one.

### 4.2 Type

Inter, self-hosted from `public/fonts/inter-variable.woff2` as one variable
file, with `system-ui` as the fallback. Self-hosted rather than from a CDN
because the deployment is local (spec §3) and must render correctly with no
network. Serials, references and asset IDs use the system mono stack.

Scale: 12px captions · 13px labels and table cells · 15px body on a desk ·
16px body on a phone · 18px section titles · 22px page titles · 28px figures ·
36px queue counts. Phone body steps up to 16px, which is also the floor that
stops iOS zooming a focused input.

Every figure uses `font-variant-numeric: tabular-nums`, so money in a column
lines up. Headings use `text-wrap: balance`.

### 4.3 Space, shape and elevation

4px spacing scale (`--space-1` to `--space-6`), with two half-steps for control
padding only. Radius: 4px for badges and inputs, 8px for cards and buttons,
12px for dialogs and sheets.

Three elevation levels and no more — raised card, popover, floating layer. A
fourth level usually means a card inside a card, which §14 rules out.

### 4.4 Status vocabulary

One `StatusBadge`, tone chosen by a lookup table in
`frontend/src/components/status.ts`. Always a shape **and** a colour **and** the
label, because colour alone fails WCAG 1.4.1. Labels are the spec's wording
exactly. Red means someone must act now, which is why Lost is *closed* and not
*blocked*: that work is over.

| Tone | Shape | Means |
|---|---|---|
| neutral | ○ | Nothing is owed yet |
| active | ◐ | Moving, with someone holding it |
| waiting | ◆ | Waiting on a person or an event |
| blocked | ▲ | Someone must act now |
| done | ● | Finished well |
| closed | ✕ | Over, not necessarily well |

| Domain | States |
|---|---|
| Lead (F02) | New *neutral* · Contacting *active* · Qualified *active* · Survey scheduled *waiting* · Lost *closed* |
| Survey revision (F03) | Draft *neutral* · Submitted *waiting* · Changes requested *blocked* · Approved *done* · Rejected *closed* · Superseded *closed* |
| Quotation (F05) | Draft *neutral* · Issued *waiting* · Accepted *done* · Rejected *closed* · Expired *closed* · Superseded *closed* |
| Package version (F04) | Draft *neutral* · Active *done* · Retired *closed*; a package with no reviewed version is "Not live" *waiting* |
| Fulfilment (F09) | Pending · Reserved · Packed · Dispatched · Delivered, plus Blocked *blocked* on a shortage |
| Installation job (F10) | Scheduled · In progress · Awaiting customer acceptance · Completed, with blocked and delayed recorded against an owner |
| Ticket (F13) | **New · Diagnosed · In progress · Awaiting customer confirmation · Closed.** Four working states plus closed, per D048 |
| Warranty (F12, derived) | In cover *done* · Expired *closed* · Replaced *neutral* |
| Stock (F08) | On hand · Reserved · Available · Dispatched · Delivered · Installed · Returned · Quarantined *blocked* |

The ticket row is the correction most worth noting: v1.0 of this document
listed an eight-state machine with Triaged, Visit Scheduled and Awaiting
Approval/Parts. D048 cut those. Triage, scheduling and waiting for a part are
facts about a ticket, not stages of it — a scheduled visit is an F10 job, and
waiting is a block with an owner.

### 4.5 Motion

Three durations, because one duration for everything is what makes an interface
feel mechanical:

| Token | Length | For |
|---|---|---|
| `--motion-instant` | 90ms | colour and opacity on hover or press |
| `--motion-fast` | 160ms | a chip, a badge, a row, a tile lift |
| `--motion-settle` | 240ms | a panel, a dialog, a sheet |

Easings: `--ease-out` entering, `--ease-in` leaving, `--ease-spring` for a
figure landing. Exits are faster than entrances.

Rules. Never animate `width`, `height`, `top` or `left`; move with `transform`
so a row does not reflow. Never `transition: all`. A focus ring appears
instantly — a ring that fades in reads as lag. Everything that moves has a
still version: under `prefers-reduced-motion: reduce` the end state is shown at
once, set once in `global.css`.

### 4.6 The four money figures

Spec §6 and F15: collections, earned revenue, cost, subsidy estimate and margin
are distinct metrics and must never be conflated in a figure or a label. A
shared tile invites exactly that mistake, so each of the four headline figures
has its own look, keyed off the metric's own `key` from the backend.

| Figure | Identity | Tag | Basis |
|---|---|---|---|
| Quoted / projected margin | Dashed edge, no shadow — not yet earned | Projected | excl. tax |
| Completed-job operational margin | Solid, blue edge and filled tag — the figure acted on | Operational | excl. tax |
| Cash collected | Green left bar | Cash in | as recorded |
| Cash paid | Ink left bar | Cash out | as recorded |

Rules. Never add two of these into one figure. Never plot two in one chart
series group without a legend using the full names. Warranty service cost
appears separately, beside the lifetime job contribution view. A subsidy
estimate never appears inside a collections figure. Every tile states the
number of records behind it and links to them, because spec F15 says a number
the director cannot trace is not trusted. The operational margin's full
definition is one tap away and is written out, because "margin" on its own is
the word people read as profit.

### 4.7 Icons

Phosphor (`@phosphor-icons/react`), imported only through
`frontend/src/design/icons.ts`. That file names each icon for what it means in
this product — `OrderIcon`, `WarrantyIcon`, `PackingIcon` — so "the icon for an
order" has one answer, and swapping the library later is one file. One visual
family, outline weight, four sizes (15/17/20/32px).

An icon beside its own label is decorative and takes `aria-hidden`. An icon
that is a control's only content needs the control to carry the label — see
`IconButton`, where `label` is both the accessible name and the tooltip. No
emoji as icons, ever.

This is a dependency beyond spec §3's list, added under rules.md §8 by owner
instruction and recorded in `decisions.md`.

---

## 5. Application shell and navigation

### 5.1 Shell

- **Sidebar** on ink, grouped in workflow order, one level deep. Items a role
  cannot use are hidden, not greyed. Collapses to an icon rail by choice at any
  width, and automatically between 900px and 1180px where a full sidebar would
  eat the table beside it. In the rail each icon carries a `title`.
- **Header** (56px, sticky): breadcrumbs left, account menu right. The account
  menu holds the name, every role the person holds, and sign out. It is a
  native popover, so Escape and clicking away close it with no script.
- **Breadcrumbs** are the navigation trail, not the record's name. On a record
  they read "Quotations › Record", because the shell does not know what the
  record is called — the reference is the page's own title.
- **Phone**: the sidebar is replaced by a bottom bar holding the first four
  destinations the role can see, plus More, which opens a sheet with
  everything and sign out. The nav order is workflow order, so the first four
  are already the right four for each role. A bar that tries to hold all
  fifteen items — what an administrator sees — cannot be hit with a thumb.
- **Three shells**: `AppShell` (staff), `BrandShell` (public enquiry form and
  login, with the array pattern), and `PresentShell` for the screens the
  customer is handed the device on. `PresentShell` keeps the product mark, so
  the person signing can see whose document it is, and carries no navigation
  and no route back into the app. The signing routes sit behind
  `RequireStaff chrome={false}`: still signed in, no staff chrome.

### 5.2 Information architecture

The real sidebar, from `frontend/src/navigation.ts`:

```
(top)        My work · Dashboard
Sales        Quotations · Enquiries · Surveys
Delivery     Orders · Packing · Schedule
Warehouse    Stock · Purchasing
Support      Tickets · Warranties
Finance      Technician pay
Catalogue    Products · Packages
```

Navigation visibility is a convenience. The backend checks every request, so
hiding a link is never a permission. Role visibility follows rules.md §4;
`navigation.ts` is the single place it is expressed for the UI.

### 5.3 Routes

```
/                                     Public enquiry form
/login                                Staff sign-in
/work                                 My work
/dashboard, /dashboard/:metricKey     Director dashboard and drill-down
/enquiries, /enquiries/new            Lead queue, staff entry
/surveys, /surveys/:id                Survey list and record
/surveys/:id/new, /surveys/:id/edit/:revisionId   Survey step form
/quotations, /quotations/new          Quotation list, generate
/quotations/:id, /quotations/:id/accept           Record, customer signing
/orders, /orders/:id                  Order list and record
/purchasing, /purchasing/new, /purchasing/:id     Purchase orders
/stock                                Stock list
/packing, /packing/:fulfilmentId      Packing queue and scan station
/schedule, /schedule/new, /schedule/:jobId        Jobs
/installations/:reportId              Installation form
/installations/:reportId/accept       Installation acceptance
/warranties, /warranties/:id          Warranty register and record
/tickets, /tickets/new, /tickets/:id  Service
/technician-pay                       Technician payables
/catalogue/products, .../new, .../:id/edit        Products
/catalogue/packages, .../:id          Package templates
```

Filters, sort and page persist in the query string using the parameter names the
API accepts; the URL is the single source of truth for list state. There is no
`/403`, `/404` or `/500` page yet — an unknown path shows a plain message, and
a refusal renders in place. Error pages are open work (§19).

---

## 6. Frontend architecture

```
frontend/
  public/fonts/     inter-variable.woff2
  src/
    api/client.ts   fetch wrapper: same-origin, CSRF, error normalisation
    design/icons.ts the icon set, named for this product
    styles/         tokens.css · global.css
    components/     shared components, each *.tsx + *.module.css
    features/       one folder per area: api.ts · types.ts · status.ts · screens
    lib/format.ts   money, quantity, date and time in Asia/Kolkata
    navigation.ts   sidebar, roles, phone bar limit
    App.tsx         every route
```

Conventions:

- **Server state only in TanStack Query.** Mutations invalidate the list and
  record they affect. No global client store.
- **Polling, not WebSockets** (spec §3.3). Data is fresh for 30s by default.
- **No arithmetic on money or measured quantities in the browser.** Values
  arrive as decimal strings and the UI formats them. Totals on forms are
  server-computed.
- **Revision checks** on every editable record; a stale edit shows the conflict
  and keeps what was typed.
- **File naming** is `snake_case` per rules.md §7. The components and features
  built before that settled use `PascalCase`; both exist today and are not
  worth a rename commit on their own.

---

## 7. Page archetypes

Building the archetype once is what keeps about forty screens consistent.

| Archetype | Anatomy | Used for |
|---|---|---|
| **List** | `PageHeader` → `FilterTabs` + `SearchInput` → `DataTable` → `Pagination` | Every collection |
| **Record** | Header with reference and status → actions → `StatusPath` → sections → `ActivityTimeline` | Lead, survey, quotation, order, job, ticket, warranty |
| **Side panel** | Floats over a list for quick work without leaving it; Escape closes and focus returns to the row | Lead triage, product edit |
| **Step form** | One section per screen on a phone, explicit draft save, sticky primary action | Survey capture, installation report |
| **Scan station** | Checklist left, scan field and last-scan result right, shortage panel | Packing |
| **Customer view** | No navigation, customer-safe data only, signature pad | Quotation and installation acceptance |
| **Dashboard** | Filter bar → tiles → ranked lists, every figure drilling down | Director dashboard |
| **My work** | One panel per role the person holds, each a count and its rows | The landing page |

---

## 8. Each role's day

| Role | Main device | Home shows | Most-used screen |
|---|---|---|---|
| Sales | Desktop | New, overdue and unassigned enquiries | Enquiry list and panel |
| Operations Manager | Desktop | Surveys to approve, blocked jobs, unscheduled jobs | Schedule, survey review |
| Warehouse | Phone or scanner | Orders to pack, shortages, receipts | Scan station |
| Technician | Phone | Today's and this week's jobs | Job record, step forms |
| Support | Desktop | Open tickets, awaiting confirmation | Serial lookup, ticket record |
| Finance | Desktop | Cleared payments, overdue balances | Order record, technician pay |
| Director | Desktop or tablet | Dashboard | Dashboard and drill-downs |
| Administrator | Desktop | Everything | Lists, Django admin for configuration |

---

## 9. Field and device UX

HTTPS is mandatory for camera scanning and signature capture (spec §10); the
localhost exception does not cover a LAN IP, so the deployment plan must provide
a trusted LAN HTTPS path for phone and tablet testing.

**Scanning (F08, F09).** The scan field keeps focus and accepts
Enter-terminated input from USB and Bluetooth keyboard-wedge scanners. Every
scan produces one result in a live region plus a visual response: accepted, or
a named rejection — wrong product · allocated to another order · already
dispatched · repeated scan · missing quantity on close. Bulk items scan the
batch or container ID and then take a counted quantity with its unit; no serial
is ever shown or requested for a length of cable. The manual fallback is
visible only to users with the permission, requires a reason, and says on
screen that it is written to the audit log.

Scan results and the action that finishes a field task are the two things
that must never be missed: the first announces through a live region, the
second sticks to the bottom of the screen rather than scrolling away.

**Signature (F06, F11).** Canvas with Pointer Events, so finger, stylus and
mouse all work. Clear is available; the customer's typed name and an explicit
acceptance are required before Accept enables. The label beside every pad:
*"Drawn signature — in-app evidence of acceptance. Not an Aadhaar eSign or a
certified digital signature."* The footer shows the document reference,
revision and content-hash prefix being accepted, and the witnessing staff
member.

**Phone behaviour.** Controls are 48px and body text 16px. Step forms save as
draft explicitly — there is no offline sync (spec §11) — and never silently
lose input when the network drops. Safe-area insets are respected top and
bottom, and the page never scrolls sideways.

---

## 10. Finding things

Each list has its own backend search; pressing `/` jumps to it. Serial lookup
is the critical path for support (F13) and reaches a unit with its warranty
status beside it.

Global search across customers, projects, assets and tickets from one entry
point is F18 and is not built. **No search box exists in the header**, because
a field that does not search is worse than no field. It lands with F18.

---

## 11. Words and numbers

| Thing | Rule | Example |
|---|---|---|
| Money | Indian grouping via `Intl.NumberFormat("en-IN")` | ₹3,00,000 |
| Tax | Say which | ₹3,00,000 incl. GST |
| Dates | Day, short month, year, in Asia/Kolkata | 31 Oct 2026 |
| Time | 12-hour with am/pm | 2:30 pm |
| Lateness | Plain words | 2 days late |
| Quantities | Always with a unit | 3 kW, 320 kWh, 28 m |
| Phone | Grouped for reading | 98765 43210 |
| References | Mono, tabular | QUO-2026-00041 |

- Use the user's words: "Mark as lost", not "Update status".
- Name buttons after what they do: "Issue quotation", not "Submit".
- Errors say what went wrong and how to fix it, and name the field.
- Honest labels from spec §6 appear on screen: "Estimated subsidy", "Advisory
  capacity", "In-app signature".
- An event time and its entered-at time both show, with the event time primary
  and "entered …" secondary.
- Weeks start Monday everywhere.

**Confirmation.** Destructive and financial actions confirm first (spec §6).
The dialog states the result: "Dispatch ORD-2026-00041? The advance of ₹90,000
is cleared. This cannot be undone." The confirm button repeats the action:
"Dispatch". Use "Are you sure?" nowhere. Reason-required variants: reversal,
refund, reschedule, correction of an actual-event time, Lost lead, reject or
request changes, reopen, manual scan.

---

## 12. States and feedback

| State | Behaviour |
|---|---|
| Loading | A still outline of the rows or cards that are coming, with the label announced. Never a shimmer |
| Empty | Say what belongs here and offer the next action. One muted glyph, no artwork |
| Error | Say what failed and offer Retry, keeping entered data |
| Permission denied | Say access is missing and who to ask |
| Saved | Update in place |
| Stale edit | Name who changed it and when; keep the user's input |

- Validation errors appear beside the field, never only at the top of a long
  form that scrolls the summary out of sight.
- A button that starts a request keeps its width, swaps its icon for a spinner
  and stops accepting clicks, so a slow action never looks like a dead one.
- An error stays until resolved.

---

## 13. Accessibility baseline

- WCAG 2.2 AA is the target.
- Colour is never the only signal (1.4.1): every status carries a shape and a
  label.
- Every interactive element has a visible focus ring and works by keyboard.
- Every input has a label; errors use `aria-invalid` and `aria-describedby`.
- Scan results and status changes announce through a live region.
- Table rows become labelled stacked cards on phones. The page never scrolls
  sideways.
- Dialogs and panels return focus to whatever opened them.
- Touch targets are at least 44px on field screens.
- Test at 200% zoom, and check phone screens outdoors in real sunlight.

---

## 14. What we will not do

The patterns that make a tool look auto-generated, or get in the way:

- Gradients as decoration, glass effects, purple-to-blue accents.
- Emoji in the interface.
- A row of big KPI tiles at the top of every page. Tiles belong on the
  dashboard, where tracing them is the point.
- "Welcome back!" banners, sparkle icons, decorative illustrations.
- Cards inside cards, or a shadow on every block.
- Full-round pills for everything.
- Loading shimmer, page transitions, parallax.
- Tracked uppercase labels. Labels, captions, table heads and nav links are the
  body face, a step smaller, sentence case, untracked.
- Decorative trend arrows or sparklines with nothing behind them.
- Fake precision such as "98.7% efficiency score", or a target the spec does
  not define.
- AI wording or features. Spec §11 excludes them.

---

## 15. Shared components

In `frontend/src/components/`, each with its own `.module.css`.

| Component | Contract |
|---|---|
| `AppShell` | Sidebar, rail, header, breadcrumbs, account menu, phone bar and More sheet |
| `BrandShell`, `BrandMark` | The ink panel for public pages; the mark and product name |
| `PresentShell` | The restricted customer view for signing: mark, document, nothing else (F06) |
| `Toast`, `ToastContext` | Brief confirmation of a completed action. Success only |
| `PageHeader` | Title, status, subtitle, back link, actions |
| `DataTable` | Columns, rows, row click, selection. Sticky head; stacked cards on a phone. Never sorts or paginates client-side |
| `Pagination` | Page numbers with a total count |
| `FilterTabs`, `SearchInput` | Saved views; debounced backend search with a `/` shortcut |
| `StateMessage` | `LoadingMessage`, `LoadingRecord`, `EmptyMessage`, `ErrorMessage` — the four states every list owes (spec §6) |
| `StatusBadge`, `status.ts` | The tone table and the badge; shape plus colour plus label |
| `StatusPath` | A record's stages, with the current one weighted |
| `Button`, `ButtonLink`, `IconButton` | primary · secondary · quiet · danger, with `icon` and `loading` |
| `ConfirmDialog` | Simple, reason-required and financial variants |
| `Field` | Labelled inputs, units, hints, field-level errors |
| `SidePanel` | Edge panel with Escape and focus return |
| `Cue` | A count and its label, as a link |
| `Reference` | Mono references and serials |
| `ActivityTimeline` | Paginated actor, action and reason history on a rail |
| `SignaturePad` | Canvas and Pointer Events, with the honest label |
| `useListParams` | List state in the URL |

Not built, and named here so nobody assumes otherwise: `FilterDrawer`,
`KanbanBoard`, `ScheduleGrid`, `NotificationBell`, `GlobalSearch`, `Toast`,
`DocumentCard`, `PhotoGrid` as a shared component, `CameraScanner`,
`ChartFrame`. Several belong to features that are not built; add them with
their feature, not before.

---

## 16. Verification

Mapped to spec §13. There is no frontend test suite and no Playwright setup
yet, so UI verification is the typecheck, the lint, the production build and a
browser walkthrough recorded in `decisions.md`.

Per change: `npm run typecheck`, `npm run lint`, `npm run build`, then a
walkthrough at 1440px, 1024px, 768px and 390px. Check that no page scrolls
sideways, that every status reads without colour, and that the per-role
navigation shows only what the role may use.

Flows that must work before a phase is called done:

1. Enquiry submitted → reference shown only after a durable save; a forced
   failure shows an explicit error with input preserved.
2. Enquiry → quotation → acceptance → order → payment → pack → dispatch →
   deliver → install → accept, end to end.
3. A repeated Confirm order creates one project and one job.
4. Two sessions reserving the same serialized unit: one succeeds, one sees a
   named failure.
5. Each scan rejection shows its own message.
6. A stale document revision is rejected on quotation and installation
   acceptance.
7. Warranty dates appear on delivery; a replacement shows both serials linked.
8. A warranty-covered repair invoices ₹0.00 with internal cost still visible to
   permitted roles.
9. A ticket cannot close without recorded customer confirmation.
10. Each dashboard tile's record count equals its drill-down list's total.
11. Every restricted screen refuses the roles that may not see it; a technician
    sees only their own jobs.
12. Camera scanning and signature work on a phone over the trusted LAN HTTPS
    path.

---

## 17. Open work in the UI

In dependency order. Nothing here changes scope; each is the UI half of a
feature `spec.md` already defines.

| Item | Needs |
|---|---|
| Screen-by-screen polish | Apply §4's tokens and §15's components across all forty screens |
| Error pages | `/403`, `/404`, `/500` as real screens |
| F19 documents | A Documents section per record, with reference, revision and generated-at |
| F20 notifications | The bell and the notification list; the queues already exist |
| F18 global search | Header search, serial-first results, audit log screen |
| F17 applications | Scheme and rule-version screens, application tracker |
| F16 Telegram | Bindings, token issue, inbox, outbox health, remote signing |

---

## 18. Decisions this document implements

Recorded in `decisions.md`: D034 (design.md as a project document), D045
(delivery tiers), D048 (four ticket states), D062 (every dashboard figure
computed from the rows its drill-down shows), D063 (dashboard is Director and
Administrator only), and the three decisions taken for this revision covering
the palette, the icon dependency and the self-hosted typeface.

---

## 19. Open questions

None of these changes the spec. Each needs an owner's answer or a feature that
is not built yet.

1. **Product name.** "Solar Ops" is a placeholder in `BrandMark.tsx`.
2. **Dark mode.** The tokens are structured for it and the semantic roles would
   carry it, but it is not in the spec and is not built.
3. **GST presentation.** Whether lines must show CGST/SGST/IGST splits depends
   on the tax configuration decision; today tax renders from the product's tax
   configuration as a single line.
4. **Payment status values** are not enumerated in F07. The UI shows what the
   backend returns.
5. **Password reset and two-step verification** are not in the spec; only
   sign-in is designed.
6. **Delivery challan.** The template has one; F19 lists no such document. Not
   built unless the owner adds it.
7. **Qualification checklist (F02).** The spec says Sales checks these items
   before qualifying; whether the system must block qualification until each is
   ticked is unspecified. Built as a recorded checklist.
8. **Duplicate-enquiry outcomes (F01).** The spec requires staff review and
   never a silent merge; the specific outcomes offered are the builders'.
9. **A `PascalCase` to `snake_case` rename** of the older component and feature
   files would settle rules.md §7, at the cost of a diff that touches every
   import. Worth doing only alongside other work in those files.

---

## 20. Sources

- `spec.md` v1.0, `rules.md`, `decisions.md`.
- Kanakku v2.1.8 admin template, structure and interaction patterns only
  (§2.1). No style values taken.
- Django 5.2, DRF, React 19, Vite 7 and TanStack Query documentation.
- WCAG 2.2 AA.
