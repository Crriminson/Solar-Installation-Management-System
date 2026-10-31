# F12 — Warranties

**Status: Verified.** This describes what was built. The evidence is in
section 11. Replacements are made from an F13 ticket, which calls the service
described in section 5.

Source of the requirement: spec.md F12, section 6 (Time, Snapshots, History,
Concurrency), section 14 (defaults) and decisions D015, D020 and D021.

## 1. What F12 is for

A customer rings up years after installation with a dead inverter. Nobody
should have to dig out a file to answer "is this covered, and until when?"

F12 makes that answer exist from the moment the goods arrive. When delivery
is recorded, the system creates one warranty record per eligible asset, by
itself. Nobody types dates into a register. Each record stays correct for
as long as it is needed: 20 years for a panel, even if the catalogue policy
changes the next day.

F12 sits between F09 and F13 in the build order. F09 gives it the trigger
(delivery). F13 reads it (is this complaint covered?) and drives
replacements.

```
F09 delivery recorded
   │  same database transaction
   ▼
F12 one warranty per eligible asset ───► F13 "is this serial covered?"
   │                                        │
   │                                        ▼
   └──────────── replacement history ◄── F13 replacement of a failed unit
```

## 2. The rules, and how each is kept

| Rule from spec.md | How it is kept |
|---|---|
| Delivery creates the record automatically | `deliver()` calls `issue_warranties()` in its own transaction. If issuing fails, the delivery rolls back too. |
| Packing and dispatch start nothing | Only `deliver()` calls it. A test checks there are no warranties after packing or after dispatch. |
| Start-inclusive, expiry-exclusive | `coverage_start <= date < coverage_expires_on`, in one method (`covers`). The stored expiry is the first day *not* covered. |
| Leap-day behaviour is explicit | `coverage_expiry()`, section 4.2. |
| Policy snapshotted at delivery | Name, version, duration, conditions and the replacement term are copied onto the warranty. |
| Later policy changes never rewrite coverage | A warranty row cannot be edited at all (`save()` refuses, `delete()` refuses). |
| Replacement inherits remaining coverage | The expiry date is copied unchanged, section 5. |
| ...unless the policy grants a fresh period | New policy flag, snapshotted, section 5. |
| Both serials retained and linked | A replacement is a new row pointing at the old one. The old row is never touched. |
| 2 years and 20 years are configuration | They already are: `WarrantyPolicy` rows loaded by a migration, edited in Django admin. |

## 3. What counts as an eligible asset

An asset is eligible when both of these hold:

1. It is a `SerializedUnit`. Warranty is per physical unit, and a metre of
   cable has no identity of its own (spec.md F08). Bulk items get no record.
2. Its product has a `warranty_policy`.

A serialized unit whose product has no policy gets no warranty, and delivery
still succeeds because the goods really did arrive. That is not hidden: it
is written to the audit event, logged, and listed as "not covered" on the
order's warranty section.

## 4. Working out the dates

### 4.1 The start date

The start date is the Asia/Kolkata calendar date of the actual delivery
time, `Fulfilment.delivered_at`. Two easy mistakes are ruled out here:

- **Not today.** Delivery can be keyed in later than it happened. Using
  `business_date()` would give every late entry a wrong start date.
- **Not the UTC date.** Timestamps are stored in UTC. A delivery at 00:15 on
  1 March in India is stored as 18:45 on 28 February UTC. Its start date is
  1 March.

`business_date()` in `apps/core/api.py` gains an optional argument for this.
Existing callers are unaffected.

### 4.2 The expiry date

Same day of the month, the policy's number of months later. If that day does
not exist, expiry moves forward to the 1st of the following month.

| Delivered | Policy | Expires (first day not covered) | Last covered day |
|---|---|---|---|
| 15 Jan 2027 | 24 months | 15 Jan 2029 | 14 Jan 2029 |
| 29 Feb 2028 | 24 months | **1 Mar 2030** (29 Feb 2030 does not exist) | 28 Feb 2030 |
| 29 Feb 2028 | 240 months | 29 Feb 2048 (a leap year, so it exists) | 28 Feb 2048 |
| 31 Jan 2027 | 1 month | **1 Mar 2027** (31 Feb does not exist) | 28 Feb 2027 |

**Why forward and not back to 28 February.** Expiry is exclusive, so
expiring on 28 February 2030 would make the last covered day 27 February,
one day short of the two years sold. Moving forward means the customer
never receives less than the full term. This is decision D049.

Python's standard library has no "add months", and rules.md section 8 says
not to add a dependency without need, so this is a short pure function in
`apps/warranties/coverage.py` using `calendar.monthrange`. The same pattern
as `catalogue/sizing.py`.

### 4.3 Status

Status is worked out on read and never stored. Otherwise a daily job would
have to flip rows to Expired, and a missed run would show an expired
warranty as active.

| Status | Meaning |
|---|---|
| In cover | Today is inside the window and the unit has not been replaced |
| Expired | Today is on or after the expiry date |
| Replaced | A replacement record points at this one |

Status answers "what about today?". F13 asks a different question, "was the
complaint in cover?", and `covers(date)` takes that date as an argument. A
slow technician visit can never expire a valid claim (D021) because the
visit date is simply not the date checked.

### 4.4 When cover actually ends

The stored expiry never changes, but a unit that has been replaced stops being
covered before it, because its cover moved to the replacement. `cover_ends_on`
is the one definition of this. Both `covers()` and the "Last covered day" on
screen use it, so the record can never promise cover that has moved to another
unit. A unit replaced on 20 January shows 19 January as its last covered day,
whatever its original expiry was.

## 5. Replacements

A replacement never edits the failed unit's warranty. It adds a new row for
the new unit with `replaces` pointing at the old row. That is what preserves
the failed unit's history, and following the links gives the replacement
history in either direction.

Terms are copied from the **original warranty's snapshot**, not from today's
catalogue. A policy change after delivery cannot alter what a replacement
receives, and a different replacement model still carries the original
terms.

Example: an inverter delivered 10 Mar 2027, covered until 10 Mar 2029, is
replaced on 20 Jan 2028.

| Case | New unit's coverage |
|---|---|
| Normal (D020): inherits | 20 Jan 2028 to 10 Mar 2029. The expiry does not move. |
| Policy grants a fresh period | 20 Jan 2028 to 20 Jan 2030. A full term from the replacement date. |

**Replaced after the original expired.** Complaint on 5 Mar 2029 (in cover),
replacement fitted on 15 Mar 2029 because of a technician backlog. The claim
is valid (D021), so the replacement happens. But nothing remains to inherit,
so the new row is stored with zero length and shows as Expired. The link and
history are kept, and the system does not invent cover nobody sold. This is
decision D050.

**Replaced twice.** Each replacement inherits from the one before, so the
original expiry carries down the chain and replacing a unit repeatedly can
never extend cover. That is the purpose of D020.

### What a replacement refuses

- A warranty that already has a replacement.
- The same unit as its own replacement.
- A unit not yet delivered to this customer, or one already in cover.
- A replacement dated in the future, or before the original's start.
- A complaint dated after the replacement.
- A complaint outside cover. Disputed cases go to authorized review (F13).
- A missing reason.

### The boundary with F13

F12 ships `record_replacement()` as a tested service with **no HTTP endpoint
and no button**. A replacement is always a ticket action. F13 owns the
physical work (reserving and issuing the new unit, returning or quarantining
the old one) and calls this service. Adding an endpoint now would let the
warranty record say a unit was swapped while stock said otherwise. This is
decision D051.

How F13 calls the service:

- The new unit is issued first, because the service refuses a unit that is not
  delivered or installed for this customer.
- It passes `complaint_at`, `replaced_at` and `reason`, plus `reviewed` when an
  operations manager has accepted a disputed claim, since that review is the
  authority on cover.
- The ticket link lives on F13's `Replacement` record, not on `AssetWarranty`.

## 6. Data model

New app `apps/warranties`, following the existing app layout: `models.py`,
`coverage.py`, `services.py`, `serializers.py`, `views.py`, `urls.py`,
`tests.py`, one migration. One record, named as in spec.md section 8.

### `AssetWarranty`

| Field | Purpose |
|---|---|
| `unit`, `customer`, `site`, `order` | What is covered and whose it is. Foreign keys, PROTECT. |
| `fulfilment` | The delivery that created it. Null on a replacement. |
| `delivered_at` | When the goods actually reached the customer. |
| `policy` | Link back to the policy, for reporting only. |
| `policy_name`, `policy_version`, `duration_months`, `conditions`, `fresh_period_on_replacement` | The snapshot. These are what count, never the live policy. |
| `coverage_basis` | Delivery, Inherited or Fresh. Why the dates are what they are. |
| `coverage_start` | First covered date, Asia/Kolkata. |
| `coverage_expires_on` | First date **not** covered. |
| `replaces` | One-to-one link to the warranty this replaced. Reverse name `replaced_by`. |
| `replacement_reason` | Required on a replacement. |
| `created_by`, `created_at` | Who and when. |

### Database constraints

Rules.md section 8 says to use the database where it can express the rule.

| Constraint | Stops |
|---|---|
| Unique (`unit`, `fulfilment`) | A repeated delivery creating a second warranty |
| `replaces` is one-to-one | Two replacements of one warranty |
| `coverage_start <= coverage_expires_on` | A backwards window |
| `duration_months > 0` | A warranty with no term |
| Exactly one origin: delivery, or replacement with a reason | A record with no explanation of where it came from |

There is deliberately no "one warranty per unit" constraint. A returned unit
could be resold, and that sale has its own coverage for a different
customer. The constraint would block a real delivery.

### Change to `WarrantyPolicy`

The spec requires a policy version and D015 requires policies to be
versioned, but today the model has neither a version nor a way to grant a
fresh period. Migration `catalogue/0005` adds:

- `version`, starting at 1. Saving a change to the terms bumps it
  automatically. Changing only the name does not.
- `fresh_period_on_replacement`, default off, so D020 is the default.
- A check that `duration_months` is above zero. Zero would make delivery
  fail on the warranty constraint.

Admin edits write an audit event with the before and after terms, so what
each version said can always be read back.

## 7. The change to delivery

`apps/fulfilment/services.py`, in `deliver()`:

1. After the delivery is recorded, call `issue_warranties(fulfilment, actor)`.
2. Refuse a `delivered_at` earlier than the order's confirmation. The
   warranty start comes from this field and cannot be edited afterwards, so
   an obvious typo must be stopped here.

The comparison is with order confirmation and not with dispatch on purpose.
`dispatched_at` is the time dispatch was *keyed in*. A warehouse that records
dispatch late could then be refused a true delivery time.

The delivery row lock already serialises two people recording the same
delivery, and the unique constraint is the backstop.

Also, the comment at `apps/installations/services.py:221` says F12 reads
installation acceptance to decide what each warranty covers. That is not how
this works: warranties start at delivery. The comment gets corrected.

## 8. API

Read-only. Warranties are created by events and never by a form.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/warranties/` | Paginated list |
| GET | `/api/v1/warranties/<id>/` | One record with its full replacement history |
| GET | `/api/v1/orders/<id>/warranties/` | An order's warranties, plus its units with no cover |

List filters: `search` (serial, asset id, customer name, phone, order
reference), `status` (`in_cover`, `expired`, `replaced`), `order`,
`customer`. Lists use `select_related`, so one page does not run one query
per row.

### Permissions

| Role | Access | Why |
|---|---|---|
| Support | Read | rules.md section 4 names warranty status |
| Operations Manager, Director | Read | Oversight |
| Sales, Warehouse, Finance | Read | Already see the order, and the customer asks them |
| Administrator | Read | All functions |
| Technician | **Denied** | Own assignments only. F13 decides what a service visit needs. |

Every role gets a permission test, as rules.md section 4 requires. Cost
never appears on these endpoints, so purchase-cost restrictions still hold.

## 9. Screens

design.md places F12 "inside asset and customer pages", but neither page
exists yet, and Support cannot reach the stock list because it shows cost.
So F12 gets its own small entry point, built from existing components.

| Screen | What it shows |
|---|---|
| **Warranties** list, new nav item | Search box, tabs for All, In cover, Expired, Replaced. Asset, serial, customer, policy, expiry, status. |
| **Warranty record** | Asset, customer and site, delivery time, policy and version, duration, conditions, coverage dates with the last covered day spelled out, replacement history. |
| **Warranties** section on the order record | That order's warranties with links, and any units with no cover. |
| **Delivered** section on the packing screen | "N warranties started", with a link. |

The record states the last covered day in words, because "expires 1 Mar
2030" is misread as covering 1 March. Coverage dates are never editable.
Loading, empty and error states use the shared components. The delivery
dialog gains one line saying the date starts every warranty and cannot be
changed afterwards.

## 10. Tests

Mapped to spec.md section 13: "Warranty start, expiry and
replacement-inheritance rules are tested, including the leap-day case."

| Area | Proves |
|---|---|
| Dates | Normal, leap day at 24 and 240 months, month-end rollover, first day covered, last day covered, expiry day not covered |
| Start date | Backdated delivery uses the delivery date. The 00:15 IST case uses 1 March, not 28 February. |
| Issuing | None after packing or dispatch. One per eligible unit on delivery. Bulk items none. No-policy units reported. |
| Atomicity | If issuing fails, the delivery rolls back |
| Snapshot | Editing a policy bumps its version and changes no existing warranty. The next delivery gets the new version. |
| Replacement | Inherit, fresh, chain, replaced after expiry. Fresh term read from the snapshot, not the live policy. Both serials reachable from either end. Original row unchanged. |
| Refusals | Every item in section 5, plus delivery before order confirmation |
| Eligibility | `covers(date)` at both boundaries, using the complaint date and not today |
| Immutability | `save()` and `delete()` refuse. Constraints reject bad rows directly. |
| API | Each search and filter, history, order view, no cost in payloads, query count stays flat |
| Permissions | Every role, plus anonymous, plus writes refused |
| Concurrency | Real threads (rules.md section 7): two simultaneous deliveries give one set of warranties, and two simultaneous replacements give one winner |
| Displayed dates | A replaced unit's last covered day is the day before the swap, and none if it was swapped on its first day |

## 11. Evidence

Run on 31 October 2026 against a throwaway PostgreSQL 16.13 in a temporary
folder, with Python 3.13.5 (spec.md says 3.12). No shared database was used.

| Check | Result |
|---|---|
| Backend suite, `manage.py test` | **386 passed**, 84 of them new, up from 302 |
| Migrations, `makemigrations --check` | No changes detected |
| `npm run typecheck`, `npm run lint`, `npm run build` | All clean |
| Deliberately breaking each rule | **15 of 15 caught** by the tests |
| Browser walkthrough in Chrome | Passed, one bug found and fixed (below) |

**Breaking the rules on purpose.** A test suite that passes first time proves
little, so each rule was broken in turn to confirm a test fails: clamping the
leap day, starting from today, starting from the UTC date, covering the expiry
day, not covering the first day, reading the live policy, restarting cover on
replacement, not closing a late window, removing the row lock, allowing edits,
not bumping the version, not issuing on delivery, not bounding the delivery
date, letting a technician in, and counting undelivered units as uncovered.

**The browser walkthrough** recorded a delivery through the real screens. Seven
warranties started: six panels at 20 years and one inverter at 2 years. Support
found the inverter by serial with no access to orders. A technician was not
offered the link and got a 403 going there directly. After a replacement, the
history showed both units from either end, with no sideways scrolling at
390px wide.

**The bug it found.** A replaced unit still showed its original expiry as its
last covered day, which would tell Support the failed unit was still covered.
All tests passed at that point, because they checked `covers()` and not the
displayed date. Section 4.4 is the fix, with tests that failed first.

## 12. Decisions recorded in decisions.md

| ID | Decision |
|---|---|
| D049 | A coverage expiry that lands on a date which does not exist moves forward to the 1st of the next month |
| D050 | A replacement made after expiry is stored with zero coverage. The link is kept and no cover is invented. |
| D051 | F12 ships replacement as a service. The write action arrives with F13. |
| D052 | Delivery cannot predate order confirmation |

## 13. Not in F12

| Item | Where it goes |
|---|---|
| Tickets, fault diagnosis, the eligibility decision on a claim | F13 |
| The stock side of a replacement | F13 |
| Global search across customers and assets | F18 |
| Warranty certificate PDF | F19 |
| Warranty cost on the dashboard | F15 |

## 14. Known limits

- **Existing dev databases need migrating.** Delivery now writes to the new
  warranty table, so `manage.py migrate` must run before anyone records a
  delivery, or the delivery fails.
- **Correcting a delivery time.** spec.md section 6 allows correcting an
  actual-event time with a reason, but no correction action exists for
  delivery yet. Warranties are immutable, so a mistyped date inside the
  allowed range stays wrong until that action is built, and it will have to
  reissue the affected warranties. Tracked here rather than built, because
  it is not an F12 requirement.
- **A product mis-set with no policy.** Units delivered that way are shown as
  not covered, but F12 has no way to add cover afterwards, since there was
  no policy to snapshot at delivery. Worth considering: have package review
  (F04) refuse a serialized product with no policy. That changes F04, so it
  needs its own instruction.
- **A return that is not a replacement does not end a warranty.** F13 only
  covers replacement. No flow exists yet for a customer simply handing a unit
  back.
- **Found during F12, not fixed: a wrong banner on delivered orders.** The
  order record says "Dispatch is held until ₹X has cleared. ₹X has cleared so
  far" once an order is delivered, because `dispatch_allowed` is only true while
  an order is Confirmed. This is F07 behaviour and outside the F12 batch. The
  warranty section now sits on that same screen, so it is easier to notice.

## 15. Files touched

**New:** `backend/apps/warranties/` (the app and its migration),
`frontend/src/features/warranties/` (list, record, order section, api, types,
status, styles).

**Changed, backend:** `catalogue/models.py`, `catalogue/admin.py`,
`catalogue/serializers.py`, new `catalogue/migrations/0005`, `core/api.py`,
`fulfilment/services.py`, `fulfilment/tests.py` (the shared fixture became a
mixin, so the concurrency tests can reuse it), `installations/services.py`
(comment only), `config/settings.py`, `config/urls.py`.

**Changed, frontend:** `App.tsx`, `navigation.ts`, `orders/order_record.tsx`,
`fulfilment/packing_screen.tsx`, `catalogue/types.ts`.

**Changed, docs:** `decisions.md` (D049 to D052 and the F12 row), this file.
