/*
  Sales enquiry queue (F01, F02).

  Every enquiry, newest first, so nothing sits unseen. Staff only — the
  rows carry customer contact details.

  Searching, filtering and paging all happen on the server, so the list
  stays correct once there are more enquiries than one page, and they
  live in the URL so a refresh or a shared link shows the same list.
*/

import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { ButtonLink } from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import Reference from "../../components/Reference";
import SearchInput from "../../components/SearchInput";
import {
  EmptyMessage,
  ErrorMessage,
  LoadingMessage,
} from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { ENQUIRY_STATUSES } from "../../components/status";
import { useListParams } from "../../components/useListParams";
import { formatDate, formatPhone, formatTime } from "../../lib/format";
import { fetchEnquiries } from "./api";
import FollowUpPanel from "./FollowUpPanel";
import NextStep from "./NextStep";
import { QUEUE_REFRESH_MS } from "./queue";
import type { EnquiryListItem } from "./types";
import styles from "./SalesQueue.module.css";
import { AddIcon } from "../../design/icons";

/* The slices managers asked for, plus the leads nobody has touched. */
const VIEWS = [
  { key: "all", label: "All" },
  { key: "new", label: "New" },
  { key: "unassigned", label: "Unassigned" },
  { key: "overdue", label: "Overdue" },
];

const COLUMNS: readonly Column<EnquiryListItem>[] = [
  {
    header: "Reference",
    render: (enquiry) => <Reference>{enquiry.reference}</Reference>,
  },
  { header: "Customer", render: (enquiry) => <CustomerCell enquiry={enquiry} /> },
  {
    header: "Site",
    render: ({ site }) => (
      <>
        {site.city}
        <div className={styles.muted}>{site.state}</div>
      </>
    ),
  },
  {
    header: "Status",
    render: (enquiry) => <StatusBadge status={ENQUIRY_STATUSES[enquiry.status]} />,
  },
  {
    header: "Received",
    render: (enquiry) => (
      <span className={styles.nowrap}>{formatDate(enquiry.created_at)}</span>
    ),
  },
  { header: "Next step", render: (enquiry) => <NextStep enquiry={enquiry} /> },
];

export default function SalesQueue() {
  const list = useListParams();

  const { data, isPending, isError, error, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["enquiries", list.search, list.view, list.page],
    queryFn: () =>
      fetchEnquiries({
        search: list.search,
        status: list.view === "new" ? "new" : undefined,
        unassigned: list.view === "unassigned",
        overdue: list.view === "overdue",
        page: list.page,
      }),
    // Keeps the old rows visible while a new search loads, instead of
    // flashing an empty table.
    placeholderData: keepPreviousData,
    refetchInterval: QUEUE_REFRESH_MS,
  });

  const selected =
    data?.results.find((enquiry) => String(enquiry.id) === list.selected) ?? null;

  return (
    <>
      <PageHeader
        title="Enquiries"
        actions={
          <ButtonLink to="/enquiries/new" variant="primary" icon={<AddIcon aria-hidden />}>
            New enquiry
          </ButtonLink>
        }
      />

      <FilterTabs
        label="Filter enquiries"
        options={VIEWS}
        value={list.view}
        onChange={list.setView}
      />

      <div className={styles.toolbar}>
        <SearchInput
          label="Search name, phone or reference"
          value={list.search}
          onSearch={list.setSearch}
        />
        {data && (
          <span className={styles.muted}>
            {data.count} {data.count === 1 ? "enquiry" : "enquiries"} · Updated{" "}
            {formatTime(dataUpdatedAt)}
          </span>
        )}
      </div>

      {isPending && <LoadingMessage label="Loading enquiries…" />}
      {isError && <ErrorMessage error={error} onRetry={refetch} />}

      {data && data.results.length === 0 && (
        <EmptyMessage>{emptyText(list.search, list.view)}</EmptyMessage>
      )}

      {data && data.results.length > 0 && (
        <>
          <DataTable
            caption="Enquiries"
            columns={COLUMNS}
            rows={data.results}
            rowKey={(enquiry) => enquiry.id}
            selectedKey={selected?.id}
            onRowClick={(enquiry) => list.setSelected(enquiry.id)}
          />
          <Pagination page={list.page} count={data.count} onChange={list.setPage} />
        </>
      )}

      {/* Keyed, so forms start clean and text typed for one customer
          can never be saved against the next. */}
      {selected && (
        <FollowUpPanel
          key={selected.id}
          enquiry={selected}
          onClose={() => list.setSelected(null)}
        />
      )}
    </>
  );
}


// ============================================================
// Helpers
// ============================================================

function CustomerCell({ enquiry }: { enquiry: EnquiryListItem }) {
  const { customer } = enquiry.site;

  return (
    <>
      {customer.full_name}
      <div className={styles.muted}>{formatPhone(customer.phone)}</div>
      {/* Flagged, not blocked: the same phone already belongs to
          another customer and a human decides whether they match. */}
      {enquiry.is_possible_duplicate && (
        <StatusBadge status={{ label: "Possible duplicate", tone: "waiting" }} />
      )}
    </>
  );
}

function emptyText(search: string, view: string) {
  if (search) return `No enquiry matches "${search}".`;
  if (view === "unassigned") return "Every open lead has an owner.";
  if (view === "overdue") return "No follow-ups are overdue.";
  if (view === "new") return "No new enquiries.";
  return "No enquiries yet. New submissions appear here.";
}
