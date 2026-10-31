# Design

How the Solar Installation Management System looks and behaves.

Status: draft for team review. Last updated: 2026-10-31.

`spec.md` leaves UI design, navigation and form layout to the builders. This
file is where those choices live. If it conflicts with `spec.md`, the spec
wins.

## 1. The idea

**Every screen answers two questions: what is waiting on me, and what happens
next?**

The company runs on WhatsApp, calls and paper registers because that is how
work gets passed along. The brief's test is that nobody has to phone anyone
(F20). So the design is built around handoffs, not modules. A person opens the
app and sees their work. A record shows who holds it now and what it is waiting
for.

Four rules follow from that:

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
| Colour | Grey everywhere | Neutral base, solar orange for actions, colour only for status | Gradients and colour-coded everything |
| Density | Giant cards, little data | 40px table rows, comfortable to scan | Spreadsheet walls at 12px |
| Type | One size for everything | A clear scale, tabular numbers, mono references | Display fonts and tracked capitals |
| Motion | None, so changes feel abrupt | 120ms on panels and hovers | Page transitions and loading shimmer |
| Personality | Nothing to remember | Dark brand panel, sun mark, status paths, four job tracks, "Waiting on" lines | Mascots and illustrations |

## 2. What we learned from others

We looked at products that excel at one thing, and at what ERP users complain
about. Studies keep finding the same pain: system complexity and difficulty
finding information. A survey of 184 users in Germany and 24 in Latvia reported
this, with both groups rating the problems alike. So navigation and findability
matter more here than visual polish.

| Product | What it does best | What we take | What we leave |
|---|---|---|---|
| **Business Central** | Role Centers | A home page per role, with cues that open their records and the most important actions first | Multi-level menus, tile colour pickers |
| **NetSuite** | Reminders from saved searches | A reminder is a live count of a saved query, so it can never drift from the data | Dashboards of many user-arranged portlets |
| **SAP Fiori** | Page types for enterprise work | Named page types: a list report to find, an object page for one item in full detail | Its size and component rules |
| **Odoo** | Records with history | Status and workflow buttons at the top of a record, activity history attached to it, edits logged | The clickable status bar. Our state changes are explicit actions (spec §9) |
| **Odoo Barcode** | Warehouse flow | Scan to open, scan to fill, large buttons, Validate at the end, typed fallback | Tapping a button to fill a line without scanning. F09 requires scans |
| **Frappe / ERPNext** | Fast navigation | Sidebar, command palette on Ctrl+K, saved filters above the list | Module pages full of shortcuts |
| **Shopify Polaris** | Index tables | Filter tabs, server search, sort, pagination, rows that open details | Bulk selection until a task needs it |
| **ServiceTitan** | Dispatch | Technicians against time, an unassigned tray, a current-time line, late jobs flagged, one-tap job status | Drag and drop at first, and offline mode, which our spec excludes |
| **Salesforce Path** | Sales stages | A stage path with short guidance on what each stage needs | Chevron graphics |
| **Linear** | Speed | Ctrl+K, `/` for search, `?` for shortcuts, searching by ID | Dark, ultra-dense styling. It suits developers, and keyboard flows do not carry to touch |
| **IBM Carbon** | Tables and status | Row height sizes, status with shape, colour and label, plain text when no action is needed | Its full component library |

Solar project tools (Sunbase and similar) confirm the shape of a long staged
pipeline, with checklists and job boards. Most of their published stages, such
as permits and utility inspection, follow other markets, so we keep the stages
in `spec.md`.

## 3. App shell

### Desktop

```
┌───────────────┬──────────────────────────────────────────────┐
│ Solar Ops     │  Enquiries                    [New enquiry]  │
│               │  All · Unassigned · Overdue                  │
│ [Search Ctrl K]│ ┌──────────────────────────────────────────┐│
│               │ │ Search name, phone or reference          ││
│ My work     6 │ └──────────────────────────────────────────┘│
│               │ Reference      Customer      Status   Next   │
│ SALES         │ ENQ-2026-00104 Asha Mehta    Waiting  Call   │
│ Enquiries     │ ENQ-2026-00103 Ravi Traders  New      None   │
│ Surveys       │ ...                                          │
│ Quotations    │                                              │
│               │                            1–25 of 130  Next │
│ ───────────   │                                              │
│ Priya S.      │                                              │
│ Sales         │                                              │
└───────────────┴──────────────────────────────────────────────┘
```

- **Dark sidebar, 232px.** It gives the app its frame and brand, and keeps the
  working area bright. Frappe's Desk moved navigation here to free up space, and
  it suits a growing number of sections. Below 900px a bottom bar replaces it.
- **Only what the role can use.** A section appears only if one of the user's
  roles allows it. The backend still enforces this.
- **Grouped in workflow order, not alphabetically.** Sales, Operations,
  Warehouse, Field, Support, Finance, Reports.
- **Text labels first.** Icons are optional and never stand alone.
- **Search sits at the top.** See section 8.

### Phone

Phones get a bottom bar with up to four items, for every role. It is
easy to reach with one hand.

```
┌──────────────────────┐
│ Today · 3 jobs       │
│ ...                  │
├──────────────────────┤
│ Today  Week  Search  │
└──────────────────────┘
```

When a role has more than four sections, the extra ones move behind a More item.

### Staff with several roles

One person may hold several roles. My Work shows one group per role, so nobody
has to switch modes. A Sales and Support person sees both queues on one page.

## 4. Page types

We use a small set of page types, as Fiori does. Pick one before designing a
screen. A new type needs a change to this file.

### My Work

The home page. It answers "what is waiting on me?"

```
My work                                     Saturday 31 Oct

SALES
 12 New enquiries      4 Overdue      3 Unassigned
 ─────────────────────────────────────────────────
 Overdue
 ENQ-2026-00098  Asha Mehta    Call back     2 days late
 ENQ-2026-00091  Ravi Traders  Send details  1 day late

SUPPORT
 5 Open tickets        1 High priority
```

- Cues are live counts. Each one opens the list with that filter applied.
- Show only cues that need action, and at most six per role.
- Below the cues, list the most urgent items, oldest first.
- A role with nothing waiting says so: "Nothing waiting on you."
- No greeting banner, no decorative chart.
- This is where F20's queues and notifications live.

### List

For finding records.

- Page title, then filter tabs, then search and filters, then the table.
- Filter tabs are saved views such as All, Unassigned and Overdue.
- Search, filters, sort and page number live in the URL (spec §6).
- 25 rows per page, with `1–25 of 130` and Previous and Next.
- The first column is the reference. The last is the next step or age.
- Clicking a row opens the record or the side panel.
- Keep a list to six columns. Text aligns left and numbers align right.
- Keep the old rows on screen while new ones load.
- Each list handles loading, empty, error and permission-denied states.

### Record

One item in full, like a Fiori object page with an Odoo-style activity history.

```
‹ Enquiries
ENQ-2026-00104                              [Move to Qualified]
Asha Mehta · 98765 43210 · Jaipur, Rajasthan        ⋯ More
◆ Contacting    Owner Priya S.    Waiting on Sales, due 2 Nov

●────●────○────○
New  Contacting  Qualified  Survey scheduled
Before qualifying: roof, consumption, grid, documents

Details   Survey   Quotations   Files

Left: the content              Right: activity, newest first
```

- **Header:** reference, name, status, owner, and "Waiting on".
- **One primary button:** the next legal action. The rest sit under More.
- **The primary action comes from the server.** Buttons reflect what the
  backend says is allowed, not a copy of its rules.
- **Status path:** shows the journey and what the current stage needs. It is
  display only. Changing state always goes through an action.
- **Activity:** every state change, note and correction, with actor and time.

### Side panel

For quick work without leaving a list. `FollowUpPanel` is the first one.

- Use it for short tasks such as logging a call. Use a Record for anything
  longer.
- The URL holds the open record, so a link or refresh keeps it open.
- It opens at 420px on desktop and full screen on a phone.
- Escape closes it and returns focus to the row.
- Resets when the record changes. Use `key={record.id}`.

### Step form

For long phone forms: survey capture, installation report.

- One column and one section at a time, with progress such as `3 of 6`.
- 48px controls and the right keyboard: numeric for measurements.
- Units sit beside the field, such as `m`, `kW` or `kWh`.
- Back keeps entered data, and the last step reviews everything.
- Offline sync is out of scope (spec §11). If the connection drops, say so
  clearly and keep the values on screen for retry.

### Scan station

For packing and dispatch. The scanner does the work, so the screen stays calm.

```
┌──────────────────────────────┐
│ ORD-2026-00041 · Packing     │
│ 7 of 12 items                │
│ ███████████░░░░░░░           │
├──────────────────────────────┤
│ ✓ Scanned  PNL-000213        │
│   540W panel · 4 of 6        │
├──────────────────────────────┤
│ Still needed                 │
│ Inverter 3 kW         0 of 1 │
│ DC cable, batch       Count  │
│ Mounting rail         0 of 4 │
├──────────────────────────────┤
│ [Manual entry]    [Close]    │
└──────────────────────────────┘
```

- The input keeps focus, so a USB or Bluetooth scanner works with no tap.
- The last scan fills the top of the screen in large type.
- A rejected scan shows the reason in plain words: "Allocated to ORD-2026-00039".
- Success and failure differ by colour, icon and sound.
- Bulk items need a batch scan and then a counted quantity.
- Manual entry needs permission and a reason, and is audited (F09).
- Close stays disabled until required quantities are met, and it says why.

### Board

For scheduling (F10).

- Technicians as rows, time as columns, with a current-time line.
- An unassigned tray sits below, as in ServiceTitan.
- Late jobs show a red outline and the word "Late".
- Assign by selecting a job and a slot. Add drag and drop later only if the
  simple version feels slow.
- Show overlap errors from the server beside the slot.

### Customer view

Staff hand a device to the customer for F06, and later for F11 and F13.

- A separate layout with no sidebar, no staff links, no margins.
- Larger type, showing the customer's document only.
- The signature area uses the full width, with a clear Sign and Clear.
- States plainly what is being accepted and which revision.
- Leaving this view needs staff to return to the app on purpose.

### Dashboard

For the Director (F15). See section 9.

### Public form

The one screen customers use directly, and the first impression of the company.
A dark brand panel says who this is, what is offered and what happens next, using
only true facts: no invented customer counts or savings. The form sits beside it
on a card. On a phone the panel shrinks so the form starts on the first screen.
The login screen uses the same panel. It should feel calm and trustworthy,
with no staff styling, and show the reference clearly on success.

## 5. Which page each feature uses

| Feature | Page types |
|---|---|
| F01 Enquiries | Public form, List, Side panel |
| F02 Follow-up | List, Side panel, My Work |
| F03 Survey | Step form (phone), List (review queue), Record |
| F04 Catalogue | List, Record |
| F05 Quotations | List, Record |
| F06 Acceptance | Customer view |
| F07 Orders and payments | List, Record, confirm dialogs |
| F08 Inventory | List, Record |
| F09 Packing and dispatch | My Work, Scan station |
| F10 Scheduling | Board, My Work (technician) |
| F11 Installation | Step form, Customer view |
| F12 Warranties | Record, inside asset and customer pages |
| F13 Support | List, Record, global search |
| F14 Costs | List, Record tabs |
| F15 Dashboard | Dashboard |
| F16 Telegram | Record activity, List for unlinked messages |
| F17 Subsidies | Quotation section, List for applications |
| F18 Search and audit | Command palette, Record activity |
| F19 Documents | A Documents tab on each Record |
| F20 Queues | My Work, notification list |

## 6. Each role's day

| Role | Main device | Home shows | Most-used screen |
|---|---|---|---|
| Sales | Desktop | New, overdue, unassigned enquiries | Enquiry list and panel |
| Operations Manager | Desktop | Surveys to approve, blocked jobs, unscheduled jobs | Board |
| Warehouse | Phone or scanner | Orders to pack, shortages, receipts | Scan station |
| Technician | Phone | Today's and this week's jobs | Job page, Step forms |
| Support | Desktop | Open tickets, unassigned, high priority | Search, ticket Record |
| Finance | Desktop | Cleared payments, overdue balances | Order Record, invoices |
| Director | Desktop or tablet | Dashboard | Dashboard, drill-downs |
| Administrator | Desktop | Users and settings | Lists |

## 7. Visual system

Keep building on `frontend/src/styles/tokens.css`. Screens never use raw colour
or font-size values.

### Colour

- The base is warm neutral. White surfaces sit on a very light background.
- **Ink** is the dark brand surface: the sidebar and the brand panel, with a
  solar array pattern and the sun mark as the app's identity.
- **Solar orange is for action only:** primary buttons, links, focus rings, and
  the current place in the app.
- One primary button per view area.
- Status colours appear only on status.
- No dark mode for now. Field use needs strong light-mode contrast first.

Add these tokens. Each text and background pair was checked against WCAG AA
contrast of 4.5:1.

```css
/* Status tones: text on tint. Contrast noted beside each. */
--tone-neutral-text: #44403c;  --tone-neutral-bg: #f5f5f4;  /* 9.42:1 */
--tone-active-text:  #1e40af;  --tone-active-bg:  #dbeafe;  /* 7.15:1 */
--tone-waiting-text: #854d0e;  --tone-waiting-bg: #fef3c7;  /* 6.15:1 */
--tone-blocked-text: #991b1b;  --tone-blocked-bg: #fee2e2;  /* 6.80:1 */
--tone-done-text:    #166534;  --tone-done-bg:    #dcfce7;  /* 6.49:1 */
--tone-closed-text:  #57534e;  --tone-closed-bg:  #e7e5e4;  /* 6.08:1 */

/* Form controls need a visible edge. 4.80:1 on white. */
--color-border-strong: #78716c;

--color-on-primary: #ffffff;
--font-mono: ui-monospace, "Cascadia Mono", Consolas, monospace;
```

Two current styles need correcting:

- The Possible duplicate badge is `#a16207` on `#fef3c7`, which is 4.42:1. Use
  the waiting tone.
- Input borders use `--color-border`, which is faint. Use
  `--color-border-strong` on form controls.

### Type

- **System fonts** stay for all text. They load instantly on a poor site
  connection, need no web request, and include the ₹ sign.
- **Monospace** for references, serials and batch IDs, so they read as codes.
- **Tabular numbers** wherever figures line up.
- Sizes come from the existing scale. Minimum 14px on desktop, 16px on phones.
- Table headers are sentence case, a step smaller. No tracked capitals, except
  the small role headings in the sidebar and My Work.

### Spacing and shape

- Use the existing spacing scale.
- Radius stays at 6px. Status badges use the same radius, not full pills.
- Borders separate things. Shadows are for floating layers only: menus, dialogs
  and side panels on small screens.
- Do not put a card around everything. Tables sit on the page surface.

### Density

| Context | Row or control height |
|---|---|
| Office tables | 40px, or two-line rows where needed |
| Office buttons and inputs | 36px to 40px |
| Field and warehouse screens | 48px minimum, 8px between targets |

WCAG's floor is 24px. 48px follows Material's guidance, chosen here because
people on site may be wearing gloves or working in a hurry.

### Status

Each status shows a shape, a colour and a label. Colour alone fails WCAG 1.4.1.
Carbon's guidance agrees, and warns that more than five or six indicators can
overwhelm a view.

Every state in the spec maps to one of six tones.

| Tone | Shape | Meaning | Examples |
|---|---|---|---|
| Neutral | ○ | Not started | New, Draft, Pending, Not Started |
| Active | ◐ | Work is moving | Contacting, In Progress, Work In Progress |
| Waiting | ◆ | Held by someone else | Submitted, Awaiting Acceptance, Awaiting Approval/Parts, Documents Pending |
| Blocked | ▲ | Someone must act now | Blocked, Overdue, Needs Correction, Changes Requested |
| Done | ● | Finished well | Approved, Accepted, Delivered, Completed, Closed, Disbursed |
| Closed | ✕ | Ended without success | Lost, Rejected, Expired, Superseded |

- **Red means someone must act.** Lost is not red, because the work is over.
- A row shows one status badge. Secondary facts stay as plain text.
- Use the exact state names from `spec.md`.

### The four job tracks

Spec section 4 says financial, delivery, installation and support statuses are
independent. This is the one component unique to this product. A project Record
shows them side by side, so nobody assumes delivered means paid.

```
Payment            Delivery         Installation        Support
◆ Balance due      ● Delivered      ◐ In Progress       ○ No open tickets
₹1,47,000 by 4 Nov 29 Oct           Crew of 3, day 2
```

## 8. Finding things and working fast

**Global search** is the critical path for support (F18). Ctrl+K opens it from
anywhere, and it finds customers, phone numbers, projects, serials and tickets.

- Results are grouped by type.
- Searching an exact reference or serial goes straight to the record.
- Phone search accepts any format, such as `+91 98765 43210`.

**Keyboard shortcuts** help desk staff and are never required.

| Key | Action |
|---|---|
| Ctrl+K | Search and go |
| `/` | Focus the list search |
| `?` | Show shortcuts |
| J, K | Next and previous row |
| Enter | Open the row |
| Esc | Close a panel or dialog |

## 9. Director dashboard

The director asks three things: which jobs made money, which lost money, and
what is unfinished. Answer those first.

```
This month ▾                          [Export CSV] [Export PDF]

Money
Quoted margin    Operational margin   Cash collected   Cash paid
₹4,20,000        ₹3,10,000            ₹18,40,000       ₹12,75,000
On 14 open jobs  On 9 completed jobs  Excludes subsidy Suppliers, labour

Jobs                                     Work
9 profitable · 2 loss-making             6 blocked · 11 outstanding
(ranked table of jobs by margin)         4 overdue enquiries
```

- The figures above are sample values for layout only.
- The four money figures stay visibly separate and each carries a plain caption
  saying what it covers. Never merge or abbreviate them (F15).
- Label it "Operational margin", never "Profit" (spec §6).
- Every figure opens the records behind it.
- Prefer ranked tables to charts. Add a chart only when change over time is the
  point. Use bars and lines from Recharts, with direct labels.
- No gauges, 3D, or donut charts with many slices.
- Show the period on screen and in every export.
- Dashboard requests must stay under 2 seconds at p95 (spec §12), so load the
  page first and let slower sections fill in.

## 10. Words and numbers

| Thing | Rule | Example |
|---|---|---|
| Money | Indian grouping via `Intl.NumberFormat("en-IN")` | ₹3,00,000 |
| Tax | Say which one | ₹3,00,000 incl. GST |
| Dates | Day, short month, year, in Asia/Kolkata | 31 Oct 2026 |
| Time | 12-hour with am/pm | 2:30 pm |
| Lateness | Plain words | 2 days late |
| Quantities | Always with a unit | 3 kW, 320 kWh, 28 m |
| Phone | Grouped for reading | 98765 43210 |

- Use the user's words: "Mark as lost", not "Update status".
- Name buttons after what they do: "Issue quotation", not "Submit".
- Errors say what went wrong and how to fix it, and name the field.
- Honest labels from spec §6 appear on screen: "Estimated subsidy", "Advisory
  capacity", "In-app signature".
- A subsidy estimate is never shown as money received or taken off a balance
  unless the payment arrangement says so.

**Confirmation.** Destructive and financial actions confirm first (spec §6).
The dialog states the result: "Dispatch ORD-2026-00041? The advance of ₹90,000
is cleared. This cannot be undone." The confirm button repeats the action:
"Dispatch". Use "Are you sure?" nowhere.

## 11. States and feedback

| State | Behaviour |
|---|---|
| Loading | Plain text or a table outline for lists. No shimmer |
| Empty | Say what belongs here and the next action. No illustration |
| Error | Say what failed and offer Retry, keeping entered data |
| Permission denied | Say the role needed, and who to ask |
| Saved | Update in place. A brief "Saved" near the action is enough |
| Stale edit | "Priya changed this at 2:30 pm. Review their change." Keep the user's input |
| Connection lost | A persistent notice. Nothing typed is cleared |

- Validation errors appear beside the field, with a summary at the top.
- Toasts are for short success messages only. An error stays until resolved.
- Refresh work queues with light polling (spec §3.3 rules out WebSockets).
  Show "Updated 2:31 pm" so people can trust what they see.

## 12. Accessibility baseline

- WCAG 2.2 AA is the target.
- Colour is never the only signal (1.4.1).
- Every interactive element has a visible focus ring and works by keyboard.
- Every input has a label. Errors use `aria-invalid` and `aria-describedby`.
- Status updates announce through a polite live region.
- Table rows become labelled stacked cards on phones. The page itself
  never scrolls sideways.
- Dialogs and panels trap focus and return it on close.
- Test with zoom at 200%, and check phone screens outdoors in real sunlight.

## 13. What we will not do

These are the patterns that make a tool look auto-generated, or get in the way:

- Gradients, glass effects or purple accents.
- Emoji in the interface.
- A row of big KPI tiles at the top of every page.
- Sparkle icons, "Welcome back!" banners or decorative illustrations.
- Cards inside cards, or a shadow on every block.
- Full-round pills for everything.
- Icon-only navigation.
- Decorative trend arrows or sparklines with no action behind them.
- Loading shimmer, page transitions or parallax.
- Tracked uppercase labels everywhere.
- Fake precision such as "98.7% efficiency score".
- AI wording or features. The spec excludes AI recommendations.

## 14. Shared components

Create these in `frontend/src/components/`, each with a `.module.css` file. Add
no UI library. This matches the CSS Modules baseline in `spec.md`.

| Build order | Component | Purpose |
|---|---|---|
| 1 | `AppShell` | Sidebar, phone bar, role-based sections |
| 1 | `BrandMark`, `BrandShell` | The sun mark, and the brand panel page layout |
| 1 | `PageHeader` | Title, status, primary action |
| 1 | `StatusBadge` | Shape, tone and label, from one status map |
| 1 | `Field` | Label, hint, error. Move it out of `EnquiryForm.tsx` |
| 2 | `DataTable` | Columns, row click, stacked cards on phones |
| 2 | `FilterTabs` | Saved views, stored in the URL |
| 2 | `Pagination` | `1–25 of 130`, Previous, Next |
| 2 | `StateMessage` | Loading, empty, error, permission denied |
| 3 | `Reference`, and `lib/format.ts` for money, dates and quantities | One way to show each value |
| 3 | `StatusPath` | Stages, current stage, short guidance |
| 3 | `ActivityTimeline` | State changes, notes, corrections |
| 3 | `ConfirmDialog` | States the result of an action |
| 3 | `SidePanel` | Width, focus, Escape, URL state |
| 4 | `Cue` | Live count that opens a filtered list |
| With F18 | `CommandSearch` | Ctrl+K. Needs the global search API |
| Later | `Icon` | A small local SVG set, once a screen needs one. Status uses shapes |
| Later | `ScanInput`, `StepForm`, `SignaturePad`, `JobTracks`, `ScheduleBoard` | Built with their features |

## 15. First steps in the existing screens

1. Add the new tokens, and fix the badge and input border.
2. Build `AppShell`, and add a staff login page. Today staff log in through
   Django admin.
3. Move `Field` into `components/`, then reuse it for address and state.
4. Rebuild `SalesQueue` as the first List: URL filters, pagination, `StatusBadge`
   and a received date.
5. Rebuild `FollowUpPanel` on `SidePanel`, with owner assignment.
6. Build My Work for Sales from the same queries.

Build new screens on these parts from then on, so F03 onward starts consistent.

## 16. Decisions to confirm

These are recommendations. Change them here if the team disagrees.

| Decision | Recommendation | Why |
|---|---|---|
| Navigation | Left sidebar | Room for many sections, as in Frappe |
| Theme | Light only for now | Outdoor legibility first. Dark mode adds testing |
| Fonts | System fonts, no web font | Fast on poor connections, no external request |
| Icons | Small local SVG set | Avoids a dependency, keeps the look consistent |
| Scheduling | Select to assign, no drag and drop yet | No extra library, works on touch |
| Bulk actions | None until a task needs them | Keeps lists simple |
| Name in the app | "Solar Ops" as a placeholder | The company name is not in the spec |

## Sources

Product and design guidance:

- [Designing Role Centers, Microsoft](https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/developer/devenv-designing-role-centers)
- [Creating and customizing Cues, Microsoft](https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/developer/devenv-cues-action-tiles)
- [Setting up reminders, NetSuite](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N581945.html) and [Displaying saved search results, NetSuite](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N689267.html)
- [Object page, SAP Fiori](https://www.sap.com/design-system/fiori-design-web/v1-84/page-types/floorplans/object-page/usage) and [List report, SAP Fiori](https://www.sap.com/design-system/fiori-design-web/v1-84/page-types/floorplans/list-report-floorplan-sap-fiori-element/usage). SAP blocks direct reading, so these points come from search excerpts. Check them in a browser.
- [View architectures, Odoo](https://www.odoo.com/documentation/19.0/developer/reference/user_interface/view_architectures.html) and [Chatter, Odoo](https://www.odoo.com/documentation/19.0/applications/productivity/discuss/chatter.html)
- [Receipts and deliveries in Barcode, Odoo](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/barcode/operations/receipts_deliveries.html)
- [Product updates December 2025, Frappe](https://frappe.io/blog/product-updates/product-updates-for-december-2025)
- [Index table, Polaris](https://polaris-react.shopify.com/components/tables/index-table) and [Resource index pattern, Shopify](https://shopify.dev/docs/api/app-home/patterns/templates/resource-index)
- [Using the dispatch board, ServiceTitan](https://help.servicetitan.com/how-to/using-dispatch-board) and [Mobile app review, third party](https://softwareconnect.com/reviews/servicetitan/)
- [Path overview, Salesforce Ben](https://www.salesforceben.com/implement-salesforce-path/) and [New sales tools, Trailhead](https://trailhead.salesforce.com/content/learn/modules/lex_migration_whatsnew/lex_migration_whatsnew_crm)
- [Navigating Linear, Linear](https://linear.app/enablement/guide/navigating-linear)
- [Data table, Carbon](https://carbondesignsystem.com/components/data-table/usage/) and [Status indicators, Carbon](https://www.carbondesignsystem.com/patterns/status-indicator-pattern)
- [Solar project management, Sunbase](https://www.sunbasedata.com/solar/solar-project-management-software). Vendor marketing, used only for pipeline shape.

Accessibility and ERP usability:

- [Use of Color, WCAG 2.2](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
- [Target Size Minimum, WCAG 2.2 explainer](https://dequeuniversity.com/rules/axe/4.8/target-size)
- [Touch target sizes across platforms](https://ezud.com/touch-target-sizes-mobile-accessibility/)
- [Lambeck et al., ECIS 2014](https://aisel.aisnet.org/ecis2014/proceedings/track12/16), [ERP usability comparison, RTU](https://itms-journals.rtu.lv/article/download/itms-2013-0011/2710) and [Topi, Lucas and Babaian, 2005](https://www.scitepress.org/Papers/2005/25223/25223.pdf)
