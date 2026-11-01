/*
  One purchase order, and the screen where goods are booked in.

  The receiving form asks each line for the identity its product
  actually supports: serials for a serialized product, a batch id and a
  quantity for a bulk one. There is no "enter a serial for the cable"
  box, because inventing one would be a lie the rest of the system would
  then have to live with (spec.md F08).
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { describeError } from "../../api/client";
import Button, { ButtonLink } from "../../components/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type Column } from "../../components/DataTable";
import { TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { ErrorMessage, LoadingRecord } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { businessToday, formatDate, formatMoney, formatQuantity } from "../../lib/format";
import { PdfIcon } from "../../design/icons";
import SupplierPayments from "../costing/supplier_payments";
import { cancelPurchaseOrder, fetchPurchaseOrder, placePurchaseOrder, receiveGoods,
         stockLabelsUrl, type ReceiptLine } from "./api";
import { PURCHASE_STATUSES } from "./status";
import type { PurchaseLine, PurchaseOrder } from "./types";
import styles from "./inventory.module.css";

const COLUMNS: readonly Column<PurchaseLine>[] = [
  {
    header: "Item",
    render: (line) => <>{line.name}<div className={styles.muted}>{line.sku}</div></>,
  },
  { header: "Tracked as", render: (line) => line.tracking_method },
  {
    header: "Ordered", numeric: true,
    render: (line) => formatQuantity(line.quantity, line.unit),
  },
  {
    header: "Received", numeric: true,
    render: (line) => formatQuantity(line.received_quantity, line.unit),
  },
  {
    header: "Outstanding", numeric: true,
    render: (line) => formatQuantity(line.outstanding_quantity, line.unit),
  },
  { header: "Unit cost", numeric: true, render: (line) => formatMoney(line.unit_cost) },
];

export default function PurchaseRecord() {
  const { purchaseId = "" } = useParams();
  const result = useQuery({
    queryKey: ["purchase-orders", purchaseId],
    queryFn: () => fetchPurchaseOrder(purchaseId),
  });

  if (result.isPending) return <LoadingRecord label="Loading purchase order…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <PurchaseDetails purchase={result.data} />;
}

function PurchaseDetails({ purchase }: { purchase: PurchaseOrder }) {
  const [receiving, setReceiving] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });

  const placing = useMutation({
    mutationFn: () => placePurchaseOrder(purchase), onSuccess: refresh,
  });
  const cancellation = useMutation({
    mutationFn: () => cancelPurchaseOrder(purchase, reason),
    onSuccess: () => { setCancelling(false); refresh(); },
  });

  const open = purchase.status === "placed" || purchase.status === "part_received";

  return <>
    <PageHeader back={{ to: "/purchasing", label: "Purchase orders" }}
      title={<Reference>{purchase.reference}</Reference>}
      subtitle={purchase.supplier_name}
      status={<StatusBadge status={PURCHASE_STATUSES[purchase.status]} />}
      actions={(purchase.status === "received" || purchase.status === "part_received") &&
        /* Barcodes to stick on the goods as they arrive, four to a page. */
        <ButtonLink to={stockLabelsUrl({ purchase_order: purchase.id })} reloadDocument
          icon={<PdfIcon aria-hidden />}>Print labels</ButtonLink>} />

    <section className={styles.section}>
      <h2>Supplier and invoice</h2>
      <dl className={styles.facts}>
        <dt>Supplier</dt><dd>{purchase.supplier_name}</dd>
        <dt>Supplier invoice</dt><dd>{purchase.supplier_invoice_reference || "Not recorded"}</dd>
        <dt>Invoice amount</dt>
        <dd>{purchase.supplier_invoice_amount
          ? formatMoney(purchase.supplier_invoice_amount) : "Not recorded"}</dd>
        <dt>Supplier paid</dt><dd>{purchase.supplier_payment_status.replace("_", " ")}</dd>
        <dt>Placed</dt>
        <dd>{purchase.placed_on ? formatDate(purchase.placed_on) : "Not yet placed"}</dd>
        <dt>Expected</dt>
        <dd>{purchase.expected_on ? formatDate(purchase.expected_on) : "No date given"}</dd>
      </dl>
    </section>

    <SupplierPayments purchaseId={purchase.id}
      hasInvoice={Boolean(purchase.supplier_invoice_amount)} />

    <section className={styles.section}>
      <h2>Lines</h2>
      <DataTable caption="Purchase order lines" columns={COLUMNS} rows={purchase.lines}
        rowKey={(line) => line.id} />
    </section>

    <div className={styles.actions}>
      {purchase.status === "draft" &&
        <Button variant="primary" onClick={() => placing.mutate()} disabled={placing.isPending}>
          Place with supplier
        </Button>}
      {open && <Button variant="primary" onClick={() => setReceiving(true)}>Receive goods</Button>}
      {purchase.status !== "cancelled" && purchase.status !== "received" &&
        <Button onClick={() => setCancelling(true)}>Cancel</Button>}
      {placing.isError && <span className={styles.error}>{describeError(placing.error)}</span>}
    </div>

    {receiving && <ReceiveForm purchase={purchase} onClose={() => setReceiving(false)}
      onSaved={() => { setReceiving(false); refresh(); }} />}

    {cancelling && <ConfirmDialog title={`Cancel ${purchase.reference}?`}
      confirmLabel="Cancel purchase order" pending={cancellation.isPending}
      error={cancellation.isError ? describeError(cancellation.error) : null}
      onConfirm={() => cancellation.mutate()} onCancel={() => setCancelling(false)}>
      <p>Only possible while nothing has been received against it.</p>
      <TextAreaField label="Why is this cancelled?" required value={reason} onChange={setReason} />
    </ConfirmDialog>}
  </>;
}

// ============================================================
// Receiving
// ============================================================

function ReceiveForm({ purchase, onClose, onSaved }: {
  purchase: PurchaseOrder; onClose: () => void; onSaved: () => void;
}) {
  const [receivedOn, setReceivedOn] = useState(businessToday());
  const [deliveryNote, setDeliveryNote] = useState("");
  const [notes, setNotes] = useState("");

  /* Serials are typed one per line; bulk lines keep a batch and amount. */
  const [serialText, setSerialText] = useState<Record<number, string>>({});
  const [batches, setBatches] = useState<Record<number, { batch: string; quantity: string }>>({});

  const outstanding = purchase.lines.filter(
    (line) => Number(line.outstanding_quantity) > 0,
  );

  function buildLines(): ReceiptLine[] {
    const rows: ReceiptLine[] = [];

    for (const line of outstanding) {
      if (line.tracking_method === "serialized") {
        const serials = (serialText[line.id] ?? "")
          .split("\n")
          .map((serial) => serial.trim())
          .filter(Boolean);
        if (serials.length > 0) rows.push({ line: line.id, serial_numbers: serials });
      } else {
        const entry = batches[line.id];
        if (entry?.batch && entry.quantity) {
          rows.push({ line: line.id, batch_id: entry.batch, quantity: entry.quantity });
        }
      }
    }
    return rows;
  }

  const rows = buildLines();
  const mutation = useMutation({
    mutationFn: () => receiveGoods(purchase.id, {
      received_on: receivedOn,
      delivery_note_reference: deliveryNote,
      notes,
      lines: rows,
    }),
    onSuccess: onSaved,
  });

  return <ConfirmDialog title={`Receive goods against ${purchase.reference}`}
    confirmLabel={`Book in ${rows.length} line${rows.length === 1 ? "" : "s"}`}
    pending={mutation.isPending}
    error={mutation.isError ? describeError(mutation.error) : null}
    onConfirm={() => mutation.mutate()} onCancel={onClose}>
    <div className={styles.form}>
      <TextField label="Date the goods arrived" type="date" required value={receivedOn}
        onChange={setReceivedOn} />
      <TextField label="Delivery note reference" value={deliveryNote}
        onChange={setDeliveryNote} />

      {outstanding.map((line) => <div key={line.id} className={styles.receiveLine}>
        <h3>{line.name} <span className={styles.muted}>{line.sku}</span></h3>
        <p className={styles.muted}>
          {formatQuantity(line.outstanding_quantity, line.unit)} outstanding
        </p>

        {line.tracking_method === "serialized"
          ? <TextAreaField label="Serial numbers, one per line"
              hint="Scan each unit. Leave empty to skip this line."
              value={serialText[line.id] ?? ""}
              onChange={(value) => setSerialText({ ...serialText, [line.id]: value })} />
          : <div className={styles.batchRow}>
              <TextField label="Batch or container id"
                hint="Whatever is printed on the drum or carton."
                value={batches[line.id]?.batch ?? ""}
                onChange={(batch) => setBatches({
                  ...batches,
                  [line.id]: { batch, quantity: batches[line.id]?.quantity ?? "" },
                })} />
              <TextField label={`Quantity in ${line.unit}`} inputMode="decimal"
                value={batches[line.id]?.quantity ?? ""}
                onChange={(quantity) => setBatches({
                  ...batches,
                  [line.id]: { batch: batches[line.id]?.batch ?? "", quantity },
                })} />
            </div>}
      </div>)}

      <TextAreaField label="Notes" value={notes} onChange={setNotes} />
    </div>
  </ConfirmDialog>;
}
