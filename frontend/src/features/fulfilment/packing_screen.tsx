/*
  The packing bench (F09).

  Built for someone holding a scanner, not a mouse. A keyboard-wedge
  scanner types the code and presses Enter, so the input stays focused
  and submits on Enter; a camera app pasting into the same box behaves
  the same. After every scan, good or bad, focus returns to the input,
  because the next thing the packer does is always scan again.

  The checklist is the whole screen. Anything still outstanding is
  visible without scrolling, so "is this box finished?" is answered by
  looking rather than by counting.
*/

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import { TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { formatDateTime, formatQuantity, nowForDateTimeInput,
         dateTimeInputToIso } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { WarrantiesStarted } from "../warranties/order_warranties";
import { closePacking, dispatchOrder, fetchFulfilment, recordDelivery, reserveStock,
         scanItem } from "./api";
import { FULFILMENT_STATUSES } from "./status";
import type { Fulfilment, PackingLine } from "./types";
import styles from "./fulfilment.module.css";
import { BlockedIcon, ConfirmIcon, ICON_SIZE } from "../../design/icons";

export default function PackingScreen() {
  const { fulfilmentId = "" } = useParams();
  const result = useQuery({
    queryKey: ["fulfilments", fulfilmentId],
    queryFn: () => fetchFulfilment(fulfilmentId),
  });

  if (result.isPending) return <LoadingMessage label="Loading packing list…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <Bench fulfilment={result.data} />;
}

function Bench({ fulfilment }: { fulfilment: Fulfilment }) {
  const user = useStaffUser();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["fulfilments"] });

  const reserving = useMutation({
    mutationFn: () => reserveStock(fulfilment), onSuccess: refresh,
  });
  const closing = useMutation({
    mutationFn: () => closePacking(fulfilment), onSuccess: refresh,
  });

  const packing = fulfilment.status === "reserved";

  return <>
    <PageHeader back={{ to: "/packing", label: "Packing" }}
      title={<Reference>{fulfilment.order_reference}</Reference>}
      subtitle={fulfilment.customer_name}
      status={<StatusBadge status={FULFILMENT_STATUSES[fulfilment.status]} />} />

    {fulfilment.status === "blocked" &&
      <p className={styles.blocked}>{fulfilment.blocked_reason}</p>}

    {fulfilment.status === "pending" && <div className={styles.actions}>
      <Button variant="primary" onClick={() => reserving.mutate()}
        disabled={reserving.isPending}>
        {reserving.isPending ? "Claiming stock…" : "Reserve stock"}
      </Button>
      {reserving.isError &&
        <span className={styles.error}>{describeError(reserving.error)}</span>}
    </div>}

    {fulfilment.status === "blocked" && <div className={styles.actions}>
      <Button onClick={() => reserving.mutate()} disabled={reserving.isPending}>
        Try reserving again
      </Button>
    </div>}

    {packing && <ScanBox fulfilment={fulfilment}
      canOverride={hasRole(user, "operations_manager")} onScanned={refresh} />}

    <section className={styles.section}>
      <h2>Checklist</h2>
      {fulfilment.lines.map((line) => <LineRow key={line.id} line={line} />)}
    </section>

    {packing && <div className={styles.actions}>
      <Button variant="primary" onClick={() => closing.mutate()}
        disabled={!fulfilment.is_complete || closing.isPending}>
        Seal the box
      </Button>
      {!fulfilment.is_complete &&
        <span className={styles.muted}>Everything has to be scanned first.</span>}
      {closing.isError &&
        <span className={styles.error}>{describeError(closing.error)}</span>}
    </div>}

    {fulfilment.status === "packed" && <DispatchPanel fulfilment={fulfilment} onDone={refresh} />}
    {fulfilment.status === "dispatched" && <DeliveryPanel fulfilment={fulfilment} onDone={refresh} />}
    {fulfilment.status === "delivered" && <DeliveredFacts fulfilment={fulfilment} />}
  </>;
}

// ============================================================
// Scanning
// ============================================================

function ScanBox({ fulfilment, canOverride, onScanned }: {
  fulfilment: Fulfilment; canOverride: boolean; onScanned: () => void;
}) {
  const [code, setCode] = useState("");
  const [quantity, setQuantity] = useState("");
  const [manual, setManual] = useState(false);
  const [manualReason, setManualReason] = useState("");
  const [lastGood, setLastGood] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () => scanItem(fulfilment.id, {
      code,
      quantity: quantity || undefined,
      entered_manually: manual,
      manual_reason: manual ? manualReason : undefined,
    }),
    onSuccess: () => {
      setLastGood(code);
      setCode("");
      setQuantity("");
      onScanned();
    },
  });

  /* A scanner fires the next code immediately; the box has to be ready. */
  useEffect(() => {
    if (!mutation.isPending) inputRef.current?.focus();
  }, [mutation.isPending, mutation.isError, lastGood]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (code.trim()) mutation.mutate();
  }

  return <form className={styles.scanBox} onSubmit={submit}>
    <label className={styles.scanLabel} htmlFor="scan-code">
      Scan a serial, asset id or batch
    </label>
    <input id="scan-code" ref={inputRef} className={styles.scanInput}
      value={code} onChange={(event) => setCode(event.target.value)}
      autoComplete="off" autoFocus
      placeholder="Point the scanner here" />

    <TextField label="Quantity (batches only)" value={quantity} onChange={setQuantity}
      inputMode="decimal" hint="Leave empty for a serialized unit." />

    {canOverride && <>
      <label className={styles.checkbox}>
        <input type="checkbox" checked={manual}
          onChange={(event) => setManual(event.target.checked)} />
        Enter by hand (label will not read)
      </label>
      {manual && <TextAreaField label="Why can this not be scanned?" required
        value={manualReason} onChange={setManualReason} />}
    </>}

    <Button type="submit" variant="primary" disabled={!code.trim() || mutation.isPending}>
      Add to the box
    </Button>

    {/* Every scan answers here, announced as well as shown: the person
        holding the scanner is looking at the box, not the screen. The
        slot keeps its height so a result never shifts the form. */}
    <div className={styles.scanResult} role="status" aria-live="polite">
      {mutation.isError && (
        <p className={styles.scanError}>
          <BlockedIcon size={ICON_SIZE.control} aria-hidden />
          {describeError(mutation.error)}
        </p>
      )}
      {!mutation.isError && lastGood && (
        <p className={styles.scanOk}>
          <ConfirmIcon size={ICON_SIZE.control} aria-hidden />
          Added {lastGood}
        </p>
      )}
    </div>
  </form>;
}

// ============================================================
// Checklist
// ============================================================

function LineRow({ line }: { line: PackingLine }) {
  return <div className={line.is_complete ? styles.lineDone : styles.line}>
    <div>
      <strong>{line.description}</strong>
      <div className={styles.muted}>{line.sku} · {line.tracking_method}</div>
    </div>
    <div className={styles.counts}>
      {/* The unit is said once: "6 of 6 piece", not "6 piece of 6 piece". */}
      {line.packed_quantity}
      {" of "}
      {formatQuantity(line.required_quantity, line.unit)}
      {!line.is_complete && <div className={styles.outstanding}>
        {formatQuantity(line.outstanding_quantity, line.unit)} to go
      </div>}
    </div>
    {line.scans.length > 0 && <ul className={styles.scanList}>
      {line.scans.map((scan) => <li key={scan.id}>
        {scan.asset_id || scan.batch_id}
        {scan.lot && ` · ${scan.quantity}`}
        {scan.entered_manually && <span className={styles.manual}> entered by hand</span>}
      </li>)}
    </ul>}
  </div>;
}

// ============================================================
// Dispatch and delivery
// ============================================================

function DispatchPanel({ fulfilment, onDone }: {
  fulfilment: Fulfilment; onDone: () => void;
}) {
  const [carrier, setCarrier] = useState("");
  const mutation = useMutation({
    mutationFn: () => dispatchOrder(fulfilment, carrier), onSuccess: onDone,
  });

  return <section className={styles.section}>
    <h2>Dispatch</h2>
    {!fulfilment.dispatch_allowed &&
      <p className={styles.blocked}>
        The money for this order has not cleared, so it cannot go out yet.
      </p>}
    <div className={styles.form}>
      <TextField label="Vehicle or consignment number" value={carrier}
        onChange={setCarrier} />
      <Button variant="primary" onClick={() => mutation.mutate()}
        disabled={!fulfilment.dispatch_allowed || mutation.isPending}>
        Dispatch
      </Button>
      {mutation.isError &&
        <span className={styles.error}>{describeError(mutation.error)}</span>}
    </div>
  </section>;
}

function DeliveryPanel({ fulfilment, onDone }: {
  fulfilment: Fulfilment; onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [deliveredAt, setDeliveredAt] = useState(nowForDateTimeInput());
  const [recipient, setRecipient] = useState("");
  const [notes, setNotes] = useState("");

  const mutation = useMutation({
    mutationFn: () => recordDelivery(fulfilment, {
      delivered_at: dateTimeInputToIso(deliveredAt),
      received_by_name: recipient,
      delivery_notes: notes,
    }),
    onSuccess: () => { setOpen(false); onDone(); },
  });

  return <section className={styles.section}>
    <h2>Delivery</h2>
    <p className={styles.muted}>
      Recording delivery makes the balance due and starts every warranty on
      this order. Packing and dispatch do neither.
    </p>
    <Button variant="primary" onClick={() => setOpen(true)}>Record delivery</Button>

    {open && <ConfirmDialog title={`Record delivery of ${fulfilment.order_reference}`}
      confirmLabel="Record delivery" pending={mutation.isPending}
      error={mutation.isError ? describeError(mutation.error) : null}
      onConfirm={() => mutation.mutate()} onCancel={() => setOpen(false)}>
      <div className={styles.form}>
        <p className={styles.muted}>
          Every warranty starts from this date, and it cannot be changed afterwards.
        </p>
        <TextField label="Who took delivery?" required value={recipient}
          onChange={setRecipient} />
        <TextField label="When did it arrive?" type="datetime-local" required
          value={deliveredAt} onChange={setDeliveredAt} />
        <TextAreaField label="Notes" value={notes} onChange={setNotes} />
      </div>
    </ConfirmDialog>}
  </section>;
}

function DeliveredFacts({ fulfilment }: { fulfilment: Fulfilment }) {
  return <section className={styles.section}>
    <h2>Delivered</h2>
    <dl className={styles.facts}>
      <dt>Received by</dt><dd>{fulfilment.received_by_name}</dd>
      <dt>Arrived</dt>
      <dd>{fulfilment.delivered_at ? formatDateTime(fulfilment.delivered_at) : "—"}</dd>
      <dt>Recorded</dt>
      <dd>{fulfilment.delivery_recorded_at
        ? formatDateTime(fulfilment.delivery_recorded_at) : "—"}</dd>
      {fulfilment.carrier_reference &&
        <><dt>Consignment</dt><dd>{fulfilment.carrier_reference}</dd></>}
      {fulfilment.delivery_notes &&
        <><dt>Notes</dt><dd>{fulfilment.delivery_notes}</dd></>}
      <WarrantiesStarted orderId={fulfilment.order} />
    </dl>
  </section>;
}
