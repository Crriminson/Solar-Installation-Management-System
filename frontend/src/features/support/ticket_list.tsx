/*
  F13 ticket queue, with the lookup on top.

  A call starts with someone holding whatever they have to hand: a name,
  a phone number, an order reference or a serial off the inverter. One
  box takes all of them, and a serial shows its warranty straight away.
*/

import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import DataTable, { type Column } from "../../components/DataTable";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import Reference from "../../components/Reference";
import SearchInput from "../../components/SearchInput";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { useListParams } from "../../components/useListParams";
import { formatDate, formatDateTime } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { WARRANTY_STATUSES } from "../warranties/status";
import { fetchTickets, lookup } from "./api";
import { TICKET_STATUSES } from "./status";
import type { TicketRow } from "./types";
import styles from "./support.module.css";

const COLUMNS: readonly Column<TicketRow>[] = [
  { header: "Ticket", render: (row) => <Reference>{row.reference}</Reference> },
  { header: "Customer", render: (row) => row.customer_name },
  { header: "Fault", render: (row) => row.fault_description },
  { header: "Cover", render: (row) => (row.covered ? "Warranty" : "Chargeable or mixed") },
  { header: "Owner", render: (row) => row.owner_name || "Nobody yet" },
  { header: "Raised", render: (row) => formatDateTime(row.complaint_at) },
  {
    header: "Status",
    render: (row) => <>
      <StatusBadge status={TICKET_STATUSES[row.status]} />
      {row.is_blocked && <div className={styles.error}>Blocked</div>}
    </>,
  },
];

const VIEWS = [
  { key: "open", label: "Open" },
  { key: "unassigned", label: "Unassigned" },
  { key: "high", label: "High priority" },
  { key: "closed", label: "Closed" },
  { key: "all", label: "All" },
];

export default function TicketList() {
  const user = useStaffUser();
  const list = useListParams("open");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const isOffice = hasRole(user, "support") || hasRole(user, "operations_manager");

  const query = new URLSearchParams(params);
  query.delete("view");
  if (list.view === "open") query.set("open", "true");
  if (list.view === "unassigned") query.set("unassigned", "true");
  if (list.view === "closed") query.set("status", "closed");
  if (list.view === "high") { query.set("open", "true"); query.set("priority", "high"); }

  const result = useQuery({
    queryKey: ["tickets", query.toString()],
    queryFn: () => fetchTickets(query),
    placeholderData: keepPreviousData,
  });

  return <>
    <PageHeader title="Support" subtitle="Find the caller, see their cover, open a ticket." />

    {isOffice && <Lookup />}

    <FilterTabs label="Ticket queue" options={VIEWS} value={list.view} onChange={list.setView} />
    <div className={styles.toolbar}>
      <SearchInput label="Search tickets" value={list.search} onSearch={list.setSearch} />
    </div>

    {result.isPending && <LoadingMessage label="Loading tickets…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data?.count === 0 && <EmptyMessage>No tickets here.</EmptyMessage>}
    {result.data && result.data.count > 0 && <>
      <DataTable caption="Tickets" columns={COLUMNS} rows={result.data.results}
        rowKey={(row) => row.id} onRowClick={(row) => navigate(`/tickets/${row.id}`)} />
      <Pagination page={list.page} count={result.data.count} onChange={list.setPage} />
    </>}
  </>;
}

function Lookup() {
  const [term, setTerm] = useState("");
  const result = useQuery({
    queryKey: ["support-lookup", term],
    queryFn: () => lookup(term),
    enabled: term.length >= 2,
  });
  const found = result.data;
  const nothing = found && found.customers.length === 0 && found.assets.length === 0;

  return <section className={styles.lookup}>
    <SearchInput label="Name, phone, order or serial" value={term} onSearch={setTerm} />
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {nothing && <p className={styles.muted}>Nothing matches that.</p>}

    {found && <ul className={styles.results}>
      {found.assets.map((asset) => <li key={asset.id} className={styles.result}>
        <span>
          <Reference>{asset.asset_id}</Reference> {asset.product_name}
          <div className={styles.muted}>
            {asset.customer_name}
            {asset.last_covered_on && ` · covered to ${formatDate(asset.last_covered_on)}`}
          </div>
        </span>
        <span className={styles.actions}>
          <StatusBadge status={WARRANTY_STATUSES[asset.status]} />
          <Link to={`/tickets/new?customer=${asset.customer}`}>Raise a ticket</Link>
        </span>
      </li>)}

      {found.customers.map((customer) => <li key={customer.id} className={styles.result}>
        <span>{customer.name}<div className={styles.muted}>{customer.phone}</div></span>
        <Link to={`/tickets/new?customer=${customer.id}`}>See equipment</Link>
      </li>)}
    </ul>}
  </section>;
}
