/* F08 purchase register: where every item in the warehouse came from. */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ButtonLink } from "../../components/Button";
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
import { fetchPurchaseOrders } from "./api";
import { PURCHASE_STATUSES } from "./status";
import type { PurchaseOrder } from "./types";
import styles from "./inventory.module.css";
import { AddIcon } from "../../design/icons";

const COLUMNS: readonly Column<PurchaseOrder>[] = [
  { header: "Purchase", render: (purchase) => <Reference>{purchase.reference}</Reference> },
  { header: "Supplier", render: (purchase) => purchase.supplier_name },
  {
    header: "Status",
    render: (purchase) => <StatusBadge status={PURCHASE_STATUSES[purchase.status]} />,
  },
  { header: "Lines", numeric: true, render: (purchase) => purchase.lines.length },
  {
    header: "Supplier invoice",
    render: (purchase) => purchase.supplier_invoice_reference || "—",
  },
  {
    header: "Placed",
    render: (purchase) => purchase.placed_on ? formatDate(purchase.placed_on) : "Not placed",
  },
];

const VIEWS = [
  { key: "all", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "placed", label: "Placed" },
  { key: "part_received", label: "Part received" },
  { key: "received", label: "Received" },
];

export default function PurchaseList() {
  const list = useListParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const query = new URLSearchParams(params);
  query.delete("view");
  if (list.view !== "all") query.set("status", list.view);

  const result = useQuery({
    queryKey: ["purchase-orders", query.toString()],
    queryFn: () => fetchPurchaseOrders(query),
    placeholderData: keepPreviousData,
  });

  return <>
    <PageHeader title="Purchase orders"
      subtitle="Stock only exists because one of these brought it in."
      actions={<ButtonLink to="/purchasing/new" variant="primary" icon={<AddIcon aria-hidden />}>New purchase order</ButtonLink>} />
    <FilterTabs label="Purchase status" options={VIEWS} value={list.view} onChange={list.setView} />
    <div className={styles.toolbar}>
      <SearchInput label="Search purchase or supplier" value={list.search}
        onSearch={list.setSearch} />
    </div>

    {result.isPending && <LoadingMessage label="Loading purchase orders…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data?.count === 0 && <EmptyMessage>No purchase orders match.</EmptyMessage>}
    {result.data && result.data.count > 0 && <>
      <DataTable caption="Purchase orders" columns={COLUMNS} rows={result.data.results}
        rowKey={(purchase) => purchase.id}
        onRowClick={(purchase) => navigate(`/purchasing/${purchase.id}`)} />
      <Pagination page={list.page} count={result.data.count} onChange={list.setPage} />
    </>}
  </>;
}
