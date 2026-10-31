/* F07 order register: what has been sold, and what is still owed on it. */

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
import { formatDate, formatMoney } from "../../lib/format";
import { ORDER_STATUSES } from "./status";
import { fetchOrders } from "./api";
import type { Order } from "./types";
import styles from "./orders.module.css";

const COLUMNS: readonly Column<Order>[] = [
  { header: "Order", render: (order) => <Reference>{order.reference}</Reference> },
  { header: "Customer", render: (order) => order.customer_name },
  { header: "Status", render: (order) => <StatusBadge status={ORDER_STATUSES[order.status]} /> },
  { header: "Value incl. GST", numeric: true, render: (order) => formatMoney(order.gross_payable) },
  { header: "Outstanding", numeric: true, render: (order) => formatMoney(order.outstanding) },
  {
    header: "Dispatch",
    render: (order) => order.dispatch_allowed
      ? "Money cleared"
      : <span className={styles.waiting}>Awaiting advance</span>,
  },
  { header: "Confirmed", render: (order) => formatDate(order.confirmed_at) },
];

const VIEWS = [
  { key: "all", label: "All" },
  { key: "confirmed", label: "Confirmed" },
  { key: "delivered", label: "Delivered" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
];

export default function OrderList() {
  const list = useListParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const query = new URLSearchParams(params);
  query.delete("view");
  if (list.view !== "all") query.set("status", list.view);

  const result = useQuery({
    queryKey: ["orders", query.toString()],
    queryFn: () => fetchOrders(query),
    placeholderData: keepPreviousData,
  });

  return <>
    <PageHeader title="Orders"
      subtitle="Confirmed from accepted quotations. Dispatch waits on cleared money." />
    <FilterTabs label="Order status" options={VIEWS} value={list.view} onChange={list.setView} />
    <div className={styles.toolbar}>
      <SearchInput label="Search order or customer" value={list.search} onSearch={list.setSearch} />
    </div>

    {result.isPending && <LoadingMessage label="Loading orders…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data?.count === 0 &&
      <EmptyMessage>No orders match. Confirm one from an accepted quotation.</EmptyMessage>}
    {result.data && result.data.count > 0 && <>
      <DataTable caption="Orders" columns={COLUMNS} rows={result.data.results}
        rowKey={(order) => order.id} onRowClick={(order) => navigate(`/orders/${order.id}`)} />
      <Pagination page={list.page} count={result.data.count} onChange={list.setPage} />
    </>}
  </>;
}
