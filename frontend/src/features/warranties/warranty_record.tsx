/*
  One warranty (F12). Read-only, because a warranty is written once.

  Dates are spelled out as first and last covered day. The stored expiry
  is exclusive, and "expires 1 March" reads as if 1 March were covered.

  The order reference is plain text here: Support reads warranties but
  not orders, so a link would be a dead end for the main reader.
*/

import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import DataTable, { type Column } from "../../components/DataTable";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { formatDate, formatDateTime } from "../../lib/format";
import { STOCK_STATUSES } from "../inventory/status";
import { fetchWarranty } from "./api";
import { COVERAGE_BASES, describeTerm, WARRANTY_STATUSES } from "./status";
import type { HistoryEntry, WarrantyDetail } from "./types";
import styles from "./warranties.module.css";

export default function WarrantyRecord() {
  const { warrantyId = "" } = useParams();
  const result = useQuery({
    queryKey: ["warranties", "detail", warrantyId],
    queryFn: () => fetchWarranty(warrantyId),
  });

  if (result.isPending) return <LoadingMessage label="Loading warranty…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <WarrantyDetails warranty={result.data} />;
}

function WarrantyDetails({ warranty }: { warranty: WarrantyDetail }) {
  return <>
    <PageHeader back={{ to: "/warranties", label: "Warranties" }}
      title={<Reference>{warranty.asset_id}</Reference>}
      subtitle={`${warranty.product_name} · ${warranty.customer_name}`}>
      <StatusBadge status={WARRANTY_STATUSES[warranty.status]} />
    </PageHeader>

    <section className={styles.section}>
      <h2>Coverage</h2>
      <dl className={styles.facts}>
        <dt>First covered day</dt><dd>{formatDate(warranty.coverage_start)}</dd>
        <dt>Last covered day</dt>
        <dd>{describeLastCovered(warranty)}</dd>
        <dt>Basis</dt><dd>{COVERAGE_BASES[warranty.coverage_basis]}</dd>
        <dt>Delivered</dt><dd>{formatDateTime(warranty.delivered_at)}</dd>
      </dl>
    </section>

    <section className={styles.section}>
      <h2>Equipment and customer</h2>
      <dl className={styles.facts}>
        <dt>Manufacturer serial</dt><dd>{warranty.serial_number || "None printed"}</dd>
        <dt>Product</dt><dd>{warranty.product_name} ({warranty.sku})</dd>
        <dt>Unit is</dt><dd><StatusBadge status={STOCK_STATUSES[warranty.unit_status]} /></dd>
        <dt>Customer</dt><dd>{warranty.customer_name}</dd>
        <dt>Site</dt><dd>{warranty.site_address}</dd>
        <dt>Order</dt><dd><Reference>{warranty.order_reference}</Reference></dd>
      </dl>
    </section>

    <section className={styles.section}>
      <h2>Policy at delivery</h2>
      <dl className={styles.facts}>
        <dt>Policy</dt><dd>{warranty.policy_name}, version {warranty.policy_version}</dd>
        <dt>Term</dt><dd>{describeTerm(warranty.duration_months)}</dd>
        <dt>If replaced</dt>
        <dd>{warranty.fresh_period_on_replacement
          ? "The replacement gets a full new term"
          : "The replacement keeps this expiry date"}</dd>
        <dt>Conditions</dt>
        <dd><p className={styles.conditions}>{warranty.conditions || "None recorded"}</p></dd>
      </dl>
    </section>

    <ReplacementHistory warranty={warranty} />
  </>;
}

/* Null means no day was ever covered, for one of two different reasons. */
function describeLastCovered(warranty: WarrantyDetail) {
  if (warranty.last_covered_on) return formatDate(warranty.last_covered_on);
  return warranty.replaced_by
    ? "None. This unit was replaced on its first day."
    : "None. This unit was fitted after the cover it replaced had ended.";
}

function ReplacementHistory({ warranty }: { warranty: WarrantyDetail }) {
  const navigate = useNavigate();

  const columns: readonly Column<HistoryEntry>[] = [
    {
      header: "Asset",
      render: (entry) => <>
        <Reference>{entry.asset_id}</Reference>
        <div className={styles.muted}>{entry.serial_number || "No serial printed"}</div>
      </>,
    },
    { header: "First covered day", render: (entry) => formatDate(entry.coverage_start) },
    {
      header: "Last covered day",
      render: (entry) => entry.last_covered_on ? formatDate(entry.last_covered_on) : "—",
    },
    { header: "Basis", render: (entry) => COVERAGE_BASES[entry.coverage_basis] },
    { header: "Reason", render: (entry) => entry.replacement_reason || "—" },
    { header: "Status", render: (entry) => <StatusBadge status={WARRANTY_STATUSES[entry.status]} /> },
  ];

  return <section className={styles.section}>
    <h2>Replacement history</h2>
    {warranty.history.length === 1
      ? <p className={styles.muted}>This unit has not been replaced.</p>
      : <DataTable caption="Replacement history" columns={columns} rows={warranty.history}
          rowKey={(entry) => entry.id} selectedKey={warranty.id}
          onRowClick={(entry) => navigate(`/warranties/${entry.id}`)} />}
  </section>;
}
