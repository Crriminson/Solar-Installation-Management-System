/*
  What a delivery left covered, shown where people look after one.

  A unit delivered with no policy gets no warranty and delivery carries
  on, because the goods really did arrive. So the gap is stated plainly
  here rather than left for a customer to discover years later.
*/

import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { describeError } from "../../api/client";
import DataTable, { type Column } from "../../components/DataTable";
import Reference from "../../components/Reference";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { fetchOrderWarranties } from "./api";
import { describeTerm, WARRANTY_STATUSES } from "./status";
import type { OrderWarranties, Warranty } from "./types";
import styles from "./warranties.module.css";

const COLUMNS: readonly Column<Warranty>[] = [
  {
    header: "Asset",
    render: (row) => <>
      <Reference>{row.asset_id}</Reference>
      <div className={styles.muted}>{row.serial_number || "No serial printed"}</div>
    </>,
  },
  { header: "Item", render: (row) => row.product_name },
  { header: "Term", render: (row) => describeTerm(row.duration_months) },
  { header: "First covered day", render: (row) => formatDate(row.coverage_start) },
  {
    header: "Last covered day",
    render: (row) => row.last_covered_on ? formatDate(row.last_covered_on) : "—",
  },
  { header: "Status", render: (row) => <StatusBadge status={WARRANTY_STATUSES[row.status]} /> },
];

function useOrderWarranties(orderId: number) {
  return useQuery({
    queryKey: ["warranties", "order", orderId],
    queryFn: () => fetchOrderWarranties(orderId),
  });
}

/* The full section on the order record. */
export default function OrderWarrantiesSection({ orderId }: { orderId: number }) {
  const result = useOrderWarranties(orderId);
  const navigate = useNavigate();

  return <section className={styles.section}>
    <h2>Warranties</h2>
    {result.isPending && <LoadingMessage label="Loading warranties…" />}
    {result.isError && <ErrorMessage error={result.error} onRetry={result.refetch} />}
    {result.data && <>
      {result.data.warranties.length === 0
        ? <p className={styles.muted}>No warranties started on this order.</p>
        : <DataTable caption="Warranties on this order" columns={COLUMNS}
            rows={result.data.warranties} rowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/warranties/${row.id}`)} />}
      <CoverageGap cover={result.data} />
    </>}
  </section>;
}

function CoverageGap({ cover }: { cover: OrderWarranties }) {
  const units = cover.uncovered_units;
  if (units.length === 0) return null;

  return <div className={styles.gap}>
    {units.length === 1 ? "1 delivered unit has" : `${units.length} delivered units have`} no
    warranty, because the product had no warranty policy.
    <ul>{units.map((unit) => <li key={unit.id}>{unit.asset_id}, {unit.product_name}</li>)}</ul>
  </div>;
}

/* One line for the packing screen's delivery facts. */
export function WarrantiesStarted({ orderId }: { orderId: number }) {
  const result = useOrderWarranties(orderId);

  return <>
    <dt>Warranties</dt>
    <dd>
      {result.isPending && "Checking…"}
      {result.isError && describeError(result.error)}
      {result.data && <Link to={`/orders/${orderId}`}>{describeStarted(result.data)}</Link>}
    </dd>
  </>;
}

function describeStarted(cover: OrderWarranties) {
  const started = cover.warranties.length;
  const missing = cover.uncovered_units.length;
  const summary = `${started} ${started === 1 ? "warranty" : "warranties"} started`;
  return missing > 0 ? `${summary}, ${missing} delivered without cover` : summary;
}
