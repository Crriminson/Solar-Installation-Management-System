/*
  What is in the warehouse, in the two shapes stock actually comes in.

  Serial lookup lives here. It is the same search that F13 will use when
  somebody rings up eighteen months later with a dead inverter, so it is
  worth it being fast and worth it finding a unit by either identity:
  our asset id or the manufacturer's serial.
*/

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import DataTable, { type Column } from "../../components/DataTable";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import Reference from "../../components/Reference";
import SearchInput from "../../components/SearchInput";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { useListParams } from "../../components/useListParams";
import { formatDate, formatMoney, formatQuantity } from "../../lib/format";
import { fetchLots, fetchUnits } from "./api";
import { STOCK_STATUSES } from "./status";
import type { BatchLot, SerializedUnit } from "./types";
import styles from "./inventory.module.css";

const UNIT_COLUMNS: readonly Column<SerializedUnit>[] = [
  { header: "Asset", render: (unit) => <Reference>{unit.asset_id}</Reference> },
  {
    header: "Manufacturer serial",
    render: (unit) => unit.serial_number
      || <span className={styles.muted}>None printed</span>,
  },
  {
    header: "Item",
    render: (unit) => <>{unit.name}<div className={styles.muted}>{unit.sku}</div></>,
  },
  { header: "Status", render: (unit) => <StatusBadge status={STOCK_STATUSES[unit.status]} /> },
  { header: "Cost", numeric: true, render: (unit) => formatMoney(unit.acquisition_cost) },
  { header: "Received", render: (unit) => formatDate(unit.created_at) },
];

const LOT_COLUMNS: readonly Column<BatchLot>[] = [
  { header: "Batch", render: (lot) => <Reference>{lot.batch_id}</Reference> },
  {
    header: "Item",
    render: (lot) => <>{lot.name}<div className={styles.muted}>{lot.sku}</div></>,
  },
  {
    header: "Quantity", numeric: true,
    render: (lot) => formatQuantity(lot.quantity, lot.unit),
  },
  { header: "Status", render: (lot) => <StatusBadge status={STOCK_STATUSES[lot.status]} /> },
  { header: "Unit cost", numeric: true, render: (lot) => formatMoney(lot.unit_cost) },
  { header: "Received", render: (lot) => formatDate(lot.created_at) },
];

const VIEWS = [
  { key: "units", label: "Serialized units" },
  { key: "lots", label: "Batch lots" },
];

export default function StockList() {
  const list = useListParams("units");
  const [params] = useSearchParams();

  const query = new URLSearchParams(params);
  query.delete("view");
  const showingUnits = list.view !== "lots";

  const units = useQuery({
    queryKey: ["stock-units", query.toString()],
    queryFn: () => fetchUnits(query),
    placeholderData: keepPreviousData,
    enabled: showingUnits,
  });
  const lots = useQuery({
    queryKey: ["stock-lots", query.toString()],
    queryFn: () => fetchLots(query),
    placeholderData: keepPreviousData,
    enabled: !showingUnits,
  });
  const result = showingUnits ? units : lots;

  return <>
    <PageHeader title="Stock"
      subtitle="Each item at the identity its physical form supports." />
    <FilterTabs label="Stock shape" options={VIEWS} value={showingUnits ? "units" : "lots"}
      onChange={list.setView} />
    <div className={styles.toolbar}>
      <SearchInput
        label={showingUnits ? "Search serial or asset id" : "Search batch id"}
        value={list.search} onSearch={list.setSearch} />
    </div>

    {result.isPending && <LoadingMessage label="Loading stock…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data?.count === 0 &&
      <EmptyMessage>Nothing here. Stock arrives through a goods receipt.</EmptyMessage>}

    {showingUnits && units.data && units.data.count > 0 && <>
      <DataTable caption="Serialized units" columns={UNIT_COLUMNS} rows={units.data.results}
        rowKey={(unit) => unit.id} />
      <Pagination page={list.page} count={units.data.count} onChange={list.setPage} />
    </>}

    {!showingUnits && lots.data && lots.data.count > 0 && <>
      <DataTable caption="Batch lots" columns={LOT_COLUMNS} rows={lots.data.results}
        rowKey={(lot) => lot.id} />
      <Pagination page={list.page} count={lots.data.count} onChange={list.setPage} />
    </>}
  </>;
}
