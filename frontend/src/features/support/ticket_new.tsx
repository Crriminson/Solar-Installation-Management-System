/*
  Raising a ticket (F13).

  Each unit shows its cover beside it, so Support can answer the caller
  before saving. The complaint time is always the server's. The optional
  earlier date is only ever a claim: it sends the ticket to review and
  decides nothing by itself (D021).
*/

import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import { SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { dateTimeInputToIso, formatDate } from "../../lib/format";
import { WARRANTY_STATUSES } from "../warranties/status";
import { fetchCustomerEquipment, raiseTicket } from "./api";
import { PRIORITIES } from "./status";
import styles from "./support.module.css";

export default function TicketNew() {
  const [params] = useSearchParams();
  const customerId = params.get("customer") ?? "";
  const navigate = useNavigate();

  const [units, setUnits] = useState<number[]>([]);
  const [fault, setFault] = useState("");
  const [code, setCode] = useState("");
  const [priority, setPriority] = useState("normal");
  const [claimed, setClaimed] = useState("");

  /* Fixed for this screen, so a double click cannot open two tickets. */
  const idempotencyKey = useRef(crypto.randomUUID());

  const equipment = useQuery({
    queryKey: ["customer-equipment", customerId],
    queryFn: () => fetchCustomerEquipment(customerId),
    enabled: Boolean(customerId),
  });

  const mutation = useMutation({
    mutationFn: () => raiseTicket({
      customer: Number(customerId), units, fault_description: fault, fault_code: code, priority,
      claimed_complaint_at: claimed ? dateTimeInputToIso(claimed) : null,
      idempotency_key: idempotencyKey.current,
    }),
    onSuccess: (ticket) => navigate(`/tickets/${ticket.id}`),
  });

  if (!customerId) return <EmptyMessage>Find the customer on the Support screen first.</EmptyMessage>;
  if (equipment.isPending) return <LoadingMessage label="Loading equipment…" />;
  if (equipment.isError) {
    return <ErrorMessage error={equipment.error} onRetry={equipment.refetch} />;
  }

  function toggle(unitId: number) {
    setUnits((chosen) => chosen.includes(unitId)
      ? chosen.filter((id) => id !== unitId) : [...chosen, unitId]);
  }

  return <>
    <PageHeader back={{ to: "/tickets", label: "Support" }} title="New ticket"
      subtitle={`${equipment.data.name} · ${equipment.data.phone}`} />

    <section className={styles.section}>
      <h2>Which equipment?</h2>
      {equipment.data.units.length === 0 &&
        <p className={styles.muted}>Nothing has been delivered to this customer yet.</p>}
      {equipment.data.units.map((unit) => <label key={unit.id} className={styles.unitPick}>
        <input type="checkbox" checked={units.includes(unit.id)}
          onChange={() => toggle(unit.id)} />
        <span>
          <Reference>{unit.asset_id}</Reference> {unit.product_name}
          <div className={styles.muted}>
            {unit.serial_number || "No serial printed"} · {unit.order_reference}
            {unit.warranty?.last_covered_on &&
              ` · covered to ${formatDate(unit.warranty.last_covered_on)}`}
          </div>
        </span>
        {unit.warranty
          ? <StatusBadge status={WARRANTY_STATUSES[unit.warranty.status]} />
          : <span className={styles.muted}>No warranty</span>}
      </label>)}
    </section>

    <section className={styles.section}>
      <h2>What is wrong?</h2>
      <div className={styles.form}>
        <TextAreaField label="Fault description" required value={fault} onChange={setFault} />
        <TextField label="Fault code" value={code} onChange={setCode} />
        <SelectField label="Priority" value={priority} options={PRIORITIES}
          onChange={setPriority} />
        <TextField label="Customer says it started earlier" type="datetime-local" value={claimed}
          onChange={setClaimed}
          hint="Only if they claim an earlier date. This sends coverage to a manager to review." />
        <Button variant="primary" onClick={() => mutation.mutate()}
          disabled={units.length === 0 || !fault.trim() || mutation.isPending}>
          Raise ticket
        </Button>
        {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}
      </div>
    </section>
  </>;
}
