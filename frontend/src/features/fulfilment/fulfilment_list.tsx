/* F09 packing queue: what the warehouse has to get out of the door. */

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
import { fetchFulfilments } from "./api";
import { FULFILMENT_STATUSES } from "./status";
import type { Fulfilment } from "./types";
import styles from "./fulfilment.module.css";

const COLUMNS: readonly Column<Fulfilment>[] = [
  { header: "Order", render: (row) => <Reference>{row.order_reference}</Reference> },
  { header: "Customer", render: (row) => row.customer_name },
  { header: "Status", render: (row) => <StatusBadge status={FULFILMENT_STATUSES[row.status]} /> },
  {
    header: "Packed",
    render: (row) => `${row.lines.filter((line) => line.is_complete).length} of ${row.lines.length} lines`,
  },
  {
    header: "Holding it up",
    render: (row) => row.status === "blocked"
      ? <span className={styles.blockedText}>Short of stock</span>
      : row.status === "packed" && !row.dispatch_allowed
        ? <span className={styles.blockedText}>Money not cleared</span>
        : "—",
  },
  { header: "Opened", render: (row) => formatDate(row.created_at) },
];

const VIEWS = [
  { key: "all", label: "All" },
  { key: "pending", label: "To reserve" },
  { key: "reserved", label: "Packing" },
  { key: "packed", label: "Ready to go" },
  { key: "blocked", label: "Short" },
  { key: "delivered", label: "Delivered" },
];

export default function FulfilmentList() {
  const list = useListParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const query = new URLSearchParams(params);
  query.delete("view");
  if (list.view !== "all") query.set("status", list.view);

  const result = useQuery({
    queryKey: ["fulfilments", query.toString()],
    queryFn: () => fetchFulfilments(query),
    placeholderData: keepPreviousData,
  });

  return <>
    <PageHeader title="Packing"
      subtitle="Every item scanned, at the identity its physical form supports." />
    <FilterTabs label="Fulfilment status" options={VIEWS} value={list.view}
      onChange={list.setView} />
    <div className={styles.toolbar}>
      <SearchInput label="Search order or customer" value={list.search}
        onSearch={list.setSearch} />
    </div>

    {result.isPending && <LoadingMessage label="Loading packing queue…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data?.count === 0 &&
      <EmptyMessage>Nothing to pack. Confirmed orders appear here.</EmptyMessage>}
    {result.data && result.data.count > 0 && <>
      <DataTable caption="Packing queue" columns={COLUMNS} rows={result.data.results}
        rowKey={(row) => row.id} onRowClick={(row) => navigate(`/packing/${row.id}`)} />
      <Pagination page={list.page} count={result.data.count} onChange={list.setPage} />
    </>}
  </>;
}
