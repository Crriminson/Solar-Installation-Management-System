/*
  Sales enquiry queue (F01).

  Every enquiry, newest first, so nothing sits unseen. Staff only — the
  rows carry customer contact details.

  Searching and ordering happen on the server, not here, so the list
  stays correct once there are more enquiries than one page.
*/

import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { fetchEnquiries } from "./api";
import FollowUpPanel from "./FollowUpPanel";
import type { EnquiryListItem } from "./types";
import styles from "./SalesQueue.module.css";

/* The three slices managers asked for: everything, nobody owns it,
   or the planned action has slipped. */
const VIEWS = [
  { key: "all", label: "All" },
  { key: "unassigned", label: "Unassigned" },
  { key: "overdue", label: "Overdue" },
] as const;

type ViewKey = (typeof VIEWS)[number]["key"];

/* Wait this long after the last keystroke before asking the server. */
const SEARCH_DEBOUNCE_MS = 300;

export default function SalesQueue() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [view, setView] = useState<ViewKey>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Debounce: the input updates on every keystroke, but the query term
  // only settles once typing pauses.
  function handleSearchChange(value: string) {
    setSearchInput(value);
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => setSearch(value), SEARCH_DEBOUNCE_MS);
  }

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["enquiries", search, view],
    queryFn: () =>
      fetchEnquiries({
        search,
        unassigned: view === "unassigned",
        overdue: view === "overdue",
      }),
    // Keeps the old rows visible while a new search loads, instead of
    // flashing an empty table.
    placeholderData: keepPreviousData,
  });

  const selected =
    data?.results.find((enquiry) => enquiry.id === selectedId) ?? null;

  return (
    <main className={styles.page}>
      <h1>Enquiries</h1>

      <div className={styles.views}>
        {VIEWS.map((option) => (
          <button
            key={option.key}
            className={option.key === view ? styles.viewActive : styles.view}
            onClick={() => setView(option.key)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.search}
          type="search"
          placeholder="Search name, phone or reference"
          value={searchInput}
          onChange={(event) => handleSearchChange(event.target.value)}
          aria-label="Search enquiries"
        />
        {data && (
          <span className={styles.count}>
            {data.count} {data.count === 1 ? "enquiry" : "enquiries"}
          </span>
        )}
      </div>

      <div className={selected ? styles.layoutSplit : styles.layout}>
        <div className={styles.listArea}>
      {isPending && <p className={styles.state}>Loading enquiries…</p>}

      {isError && (
        <p className={styles.error} role="alert">
          Could not load enquiries. {(error as Error).message}
        </p>
      )}

      {data && data.results.length === 0 && (
        <p className={styles.state}>
          {search
            ? `No enquiry matches "${search}".`
            : "No enquiries yet. New submissions appear here straight away."}
        </p>
      )}

      {data && data.results.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Customer</th>
              <th>Site</th>
              <th>Wants</th>
              <th>Electricity</th>
              <th>Next action</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((enquiry) => (
              <EnquiryRow
                key={enquiry.id}
                enquiry={enquiry}
                isSelected={enquiry.id === selectedId}
                onSelect={() => setSelectedId(enquiry.id)}
              />
            ))}
          </tbody>
        </table>
      )}
        </div>

        {selected && (
          <FollowUpPanel
            enquiry={selected}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>
    </main>
  );
}


// ============================================================
// Helpers
// ============================================================

/* Module-level so the timer survives re-renders. */
let debounceTimer = 0;

function EnquiryRow({
  enquiry,
  isSelected,
  onSelect,
}: {
  enquiry: EnquiryListItem;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const { site } = enquiry;

  return (
    <tr
      onClick={onSelect}
      className={isSelected ? styles.rowSelected : styles.row}
      tabIndex={0}
      onKeyDown={(event) => event.key === "Enter" && onSelect()}
    >
      <td className={styles.reference}>{enquiry.reference}</td>

      <td>
        {site.customer.full_name}
        <div className={styles.muted}>{site.customer.phone}</div>
        {/* Flagged, not blocked: the same phone already belongs to
            another customer and a human decides whether they match. */}
        {enquiry.is_possible_duplicate && (
          <span className={styles.duplicate}>Possible duplicate</span>
        )}
      </td>

      <td>
        {site.city}
        <div className={styles.muted}>{site.state}</div>
      </td>

      <td>
        {describeSystemType(enquiry.requested_system_type)}
        {enquiry.requested_capacity_kw && (
          <div className={styles.muted}>{enquiry.requested_capacity_kw} kW</div>
        )}
      </td>

      {/* Bill and units are shown separately. Neither implies the
          other, so we never display one in place of a missing other. */}
      <td>
        {enquiry.monthly_bill_amount ? (
          <>₹{enquiry.monthly_bill_amount}/month</>
        ) : (
          <span className={styles.muted}>Bill not given</span>
        )}
        {enquiry.monthly_consumption_kwh && (
          <div className={styles.muted}>{enquiry.monthly_consumption_kwh} kWh</div>
        )}
      </td>

      <td>
        {enquiry.next_action || (
          <span className={styles.needsAction}>Nothing planned</span>
        )}
        {enquiry.next_action_due && (
          <div className={enquiry.is_overdue ? styles.overdue : styles.muted}>
            due {enquiry.next_action_due}
          </div>
        )}
        <div className={styles.muted}>
          {enquiry.owner_name || "unassigned"}
        </div>
      </td>
    </tr>
  );
}

function describeSystemType(type: EnquiryListItem["requested_system_type"]) {
  if (type === "on_grid") return "On-grid";
  if (type === "off_grid") return "Off-grid";
  return "Not decided";
}

