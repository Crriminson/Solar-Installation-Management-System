/*
  F12 warranty register.

  The question it exists for arrives on the phone: "is this covered, and
  until when?" So a search takes whatever the caller has to hand, and
  the last covered day sits in the row rather than behind a click.
*/

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import DataTable, { type Column } from "../../components/DataTable";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import Reference from "../../components/Reference";
import SearchInput from "../../components/SearchInput";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { useListParams } from "../../components/useListParams";
import { formatDate } from "../../lib/format";
import { fetchWarranties } from "./api";
import { describeTerm, WARRANTY_STATUSES } from "./status";
import type { Warranty } from "./types";
import styles from "./warranties.module.css";

const COLUMNS: readonly Column<Warranty>[] = [
  {
    header: "Asset",
    render: (row) => <>
      <Reference>{row.asset_id}</Reference>
      <div className={styles.muted}>{row.serial_number || "No serial printed"}</div>
    </>,
  },
  {
    header: "Item",
    render: (row) => <>{row.product_name}<div className={styles.muted}>{row.sku}</div></>,
  },
  {
    header: "Customer",
    render: (row) => <>{row.customer_name}
      <div className={styles.muted}>{row.order_reference}</div></>,
  },
  { header: "Term", render: (row) => describeTerm(row.duration_months) },
  {
    header: "Last covered day",
    render: (row) => row.last_covered_on ? formatDate(row.last_covered_on) : "—",
  },
  { header: "Status", render: (row) => <StatusBadge status={WARRANTY_STATUSES[row.status]} /> },
];

const VIEWS = [
  { key: "all", label: "All" },
  { key: "in_cover", label: "In cover" },
  { key: "expired", label: "Expired" },
  { key: "replaced", label: "Replaced" },
];

export default function WarrantyList() {
  const list = useListParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const query = new URLSearchParams(params);
  query.delete("view");
  if (list.view !== "all") query.set("status", list.view);

  const result = useQuery({
    queryKey: ["warranties", query.toString()],
    queryFn: () => fetchWarranties(query),
    placeholderData: keepPreviousData,
  });

  return <>
    <PageHeader title="Warranties"
      subtitle="Started by delivery. Nobody types these dates in." />
    <FilterTabs label="Warranty status" options={VIEWS} value={list.view}
      onChange={list.setView} />
    <div className={styles.toolbar}>
      <SearchInput label="Search serial, asset, customer, phone or order"
        value={list.search} onSearch={list.setSearch} />
    </div>

    {result.isPending && <LoadingMessage label="Loading warranties…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data?.count === 0 &&
      <EmptyMessage>Nothing here. A warranty starts when a delivery is recorded.</EmptyMessage>}
    {result.data && result.data.count > 0 && <>
      <DataTable caption="Warranties" columns={COLUMNS} rows={result.data.results}
        rowKey={(row) => row.id} onRowClick={(row) => navigate(`/warranties/${row.id}`)} />
      <Pagination page={list.page} count={result.data.count} onChange={list.setPage} />
    </>}
  </>;
}
