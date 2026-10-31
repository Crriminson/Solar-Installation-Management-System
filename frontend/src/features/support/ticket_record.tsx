/*
  One ticket (F13).

  Buttons come from the server's allowed_actions, not a copy of its
  rules. Every action here is the same shape, a small form and a post,
  so they share one dialog described by a list of fields.

  Coverage sits at the top of the screen and cost only appears for those
  the server sends it to. Closing is deliberately its own step, worded as
  the customer's confirmation, because finishing the work is not it.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { apiGet, describeError } from "../../api/client";
import Button from "../../components/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type Column } from "../../components/DataTable";
import { FileField, SelectField, TextAreaField, TextField, type Option } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { dateTimeInputToIso, formatDate, formatDateTime, formatMoney, formatQuantity,
         nowForDateTimeInput } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchProductChoices } from "../catalogue/api";
import { bookVisit, fetchTicket, reviewAsset, ticketAction, uploadTicketPhoto } from "./api";
import { ASSESSMENTS, DISPOSITIONS, ESTIMATE_STATUSES, TICKET_STATUSES } from "./status";
import type { RepairEstimate, Ticket, TicketAsset, WorkLine } from "./types";
import styles from "./support.module.css";

interface StaffChoice { id: number; name: string; roles: string[] }

interface DialogField {
  name: string;
  label: string;
  kind?: "text" | "area" | "select";
  options?: readonly Option[];
  required?: boolean;
  initial?: string;
}

interface ActionSpec {
  title: string;
  confirm: string;
  note?: string;
  fields: readonly DialogField[];
  submit: (values: Record<string, string>) => Promise<unknown>;
}

export default function TicketRecord() {
  const { ticketId = "" } = useParams();
  const result = useQuery({
    queryKey: ["tickets", "detail", ticketId], queryFn: () => fetchTicket(ticketId),
  });

  if (result.isPending) return <LoadingMessage label="Loading ticket…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <TicketDetails ticket={result.data} />;
}

function TicketDetails({ ticket }: { ticket: Ticket }) {
  const user = useStaffUser();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tickets"] });
  const [dialog, setDialog] = useState<ActionSpec | null>(null);

  const isOffice = hasRole(user, "support") || hasRole(user, "operations_manager");
  const isManager = hasRole(user, "operations_manager");
  const canWork = isOffice || hasRole(user, "technician");

  const staff = useQuery({
    queryKey: ["staff"], queryFn: () => apiGet<StaffChoice[]>("staff/"), enabled: isOffice,
  });
  const products = useQuery({
    queryKey: ["product-choices"], queryFn: fetchProductChoices, enabled: canWork,
  });

  const allowed = (action: string) => ticket.allowed_actions.includes(action);
  const staffOptions = (staff.data ?? []).map((person) => ({
    value: String(person.id), label: person.name,
  }));
  const crewOptions = (staff.data ?? [])
    .filter((person) => person.roles.includes("technician"))
    .map((person) => ({ value: String(person.id), label: person.name }));
  const productOptions = (products.data ?? []).map((product) => ({
    value: String(product.id), label: `${product.sku} ${product.name}`,
  }));
  const assetOptions = ticket.assets.map((asset) => ({
    value: String(asset.id), label: `${asset.asset_id} ${asset.product_name}`,
  }));
  const visitOptions = ticket.visits.map((visit) => ({
    value: String(visit.id), label: `${formatDateTime(visit.starts_at)}, ${visit.technicians.join(", ")}`,
  }));

  const act = (action: string, body: Record<string, unknown> = {}) =>
    ticketAction(ticket, action, body);

  const specs: Record<string, ActionSpec> = {
    assign: {
      title: "Assign this ticket", confirm: "Assign",
      fields: [{ name: "owner", label: "Owner", kind: "select", options: staffOptions, required: true }],
      submit: (values) => act("assign", { owner: Number(values.owner) }),
    },
    block: {
      title: "Record what this is waiting on", confirm: "Record block",
      fields: [
        { name: "reason", label: "Waiting on", kind: "area", required: true },
        { name: "owner", label: "Who will clear it", kind: "select", options: staffOptions, required: true },
      ],
      submit: (values) => act("block", { reason: values.reason, owner: Number(values.owner) }),
    },
    visit: {
      title: "Book a service visit", confirm: "Book visit",
      note: "The technician's diary is checked, exactly as for any other job.",
      fields: [
        { name: "technician", label: "Technician", kind: "select", options: crewOptions, required: true },
        { name: "starts_at", label: "Starts", required: true, initial: nowForDateTimeInput() },
        { name: "ends_at", label: "Ends", required: true, initial: nowForDateTimeInput() },
      ],
      submit: (values) => bookVisit(ticket, {
        starts_at: dateTimeInputToIso(values.starts_at),
        ends_at: dateTimeInputToIso(values.ends_at),
        technicians: [Number(values.technician)],
      }),
    },
    diagnose: {
      title: "Record the diagnosis", confirm: "Record diagnosis",
      note: "Nothing chargeable or covered goes ahead without this.",
      fields: [
        { name: "job", label: "From which visit", kind: "select", options: visitOptions, required: true },
        { name: "findings", label: "What was found", kind: "area", required: true },
        { name: "recommendation", label: "Recommended work", kind: "area", required: true },
      ],
      submit: (values) => act("diagnose", {
        job: Number(values.job), findings: values.findings, recommendation: values.recommendation,
      }),
    },
    estimate: {
      title: "Raise an estimate", confirm: "Raise estimate",
      note: "Priced from the catalogue. This replaces any estimate still live, so the customer "
        + "decides afresh.",
      fields: [
        { name: "product", label: "Part or labour", kind: "select", options: productOptions, required: true },
        { name: "quantity", label: "Quantity", required: true, initial: "1" },
      ],
      submit: (values) => act("estimate", {
        lines: [{ product: Number(values.product), quantity: values.quantity }],
      }),
    },
    "work-line": {
      title: "Record parts or labour used", confirm: "Record",
      note: "Covered units charge the customer nothing. The internal cost is kept either way.",
      fields: [
        { name: "asset", label: "On which unit", kind: "select", options: assetOptions, required: true },
        { name: "product", label: "Part or labour", kind: "select", options: productOptions, required: true },
        { name: "quantity", label: "Quantity", required: true, initial: "1" },
      ],
      submit: (values) => act("work-line", {
        asset: Number(values.asset), product: Number(values.product), quantity: values.quantity,
      }),
    },
    replace: {
      title: "Replace a unit", confirm: "Replace unit",
      note: "Issues the new unit from stock and takes the old one back. Covered cover moves across.",
      fields: [
        { name: "asset", label: "Failed unit", kind: "select", options: assetOptions, required: true },
        { name: "code", label: "New unit: serial or asset id", required: true },
        { name: "disposition", label: "Old unit", kind: "select", options: DISPOSITIONS, required: true, initial: "quarantined" },
        { name: "reason", label: "Why", kind: "area", required: true },
      ],
      submit: (values) => act("replace", { ...values, asset: Number(values.asset) }),
    },
    confirm: {
      title: "Record the customer's confirmation", confirm: "Close ticket",
      note: "Only the customer's word closes a ticket.",
      fields: [{ name: "customer_name", label: "Who confirmed it", required: true }],
      submit: (values) => act("confirm", values),
    },
    "send-back": {
      title: "The customer says it is not fixed", confirm: "Send back",
      fields: [{ name: "reason", label: "What is still wrong", kind: "area", required: true }],
      submit: (values) => act("send-back", values),
    },
    reopen: {
      title: "Reopen this ticket", confirm: "Reopen",
      fields: [{ name: "reason", label: "Why", kind: "area", required: true }],
      submit: (values) => act("reopen", values),
    },
  };

  const quick = useMutation({
    mutationFn: (action: string) => act(action), onSuccess: refresh,
  });

  return <>
    <PageHeader back={{ to: "/tickets", label: "Support" }}
      title={<Reference>{ticket.reference}</Reference>}
      subtitle={`${ticket.customer_name}${ticket.customer_phone ? ` · ${ticket.customer_phone}` : ""}`}>
      <StatusBadge status={TICKET_STATUSES[ticket.status]} />
    </PageHeader>

    {ticket.is_blocked && <p className={styles.blocked}>Blocked: {ticket.blocked_reason}</p>}

    <div className={styles.actions}>
      {canWork && allowed("diagnose") && ticket.visits.length > 0 &&
        <Button variant="primary" onClick={() => setDialog(specs.diagnose)}>Record diagnosis</Button>}
      {isOffice && allowed("visit") &&
        <Button onClick={() => setDialog(specs.visit)}>Book a visit</Button>}
      {canWork && allowed("start-work") &&
        <Button variant="primary" onClick={() => quick.mutate("start-work")}
          disabled={quick.isPending}>Start the work</Button>}
      {canWork && allowed("work-line") &&
        <Button onClick={() => setDialog(specs["work-line"])}>Record parts or labour</Button>}
      {canWork && allowed("replace") &&
        <Button onClick={() => setDialog(specs.replace)}>Replace a unit</Button>}
      {canWork && allowed("finish") &&
        <Button variant="primary" onClick={() => quick.mutate("finish")}
          disabled={quick.isPending}>Finish the work</Button>}
      {isOffice && allowed("confirm") &&
        <Button variant="primary" onClick={() => setDialog(specs.confirm)}>Customer confirmed</Button>}
      {isOffice && allowed("send-back") &&
        <Button onClick={() => setDialog(specs["send-back"])}>Not fixed</Button>}
      {isOffice && allowed("reopen") &&
        <Button onClick={() => setDialog(specs.reopen)}>Reopen</Button>}
      {isOffice && <Button onClick={() => setDialog(specs.assign)}>Assign</Button>}
      {isOffice && ticket.status !== "closed" && (ticket.is_blocked
        ? <Button onClick={() => quick.mutate("unblock")} disabled={quick.isPending}>Clear block</Button>
        : <Button onClick={() => setDialog(specs.block)}>Record a block</Button>)}
    </div>
    {quick.isError && <p className={styles.error}>{describeError(quick.error)}</p>}

    <section className={styles.section}>
      <h2>The complaint</h2>
      <dl className={styles.facts}>
        <dt>Fault</dt><dd>{ticket.fault_description}</dd>
        {ticket.fault_code && <><dt>Fault code</dt><dd>{ticket.fault_code}</dd></>}
        <dt>Recorded</dt><dd>{formatDateTime(ticket.complaint_at)}</dd>
        {ticket.claimed_complaint_at && <>
          <dt>Customer claims</dt><dd>{formatDateTime(ticket.claimed_complaint_at)}</dd>
        </>}
        <dt>Owner</dt><dd>{ticket.owner_name || "Nobody yet"}</dd>
        <dt>Site</dt><dd>{ticket.site_address}</dd>
        <dt>Order</dt><dd><Reference>{ticket.order_reference}</Reference></dd>
      </dl>
    </section>

    <Equipment ticket={ticket} isManager={isManager} onChanged={refresh} />

    <section className={styles.section}>
      <h2>Visits and diagnosis</h2>
      {ticket.visits.length === 0
        ? <p className={styles.muted}>No visit booked yet.</p>
        : <ul className={styles.results}>{ticket.visits.map((visit) =>
            <li key={visit.id} className={styles.result}>
              <Link to={`/schedule/${visit.id}`}>{formatDateTime(visit.starts_at)}</Link>
              <span className={styles.muted}>{visit.technicians.join(", ")} · {visit.status.replace("_", " ")}</span>
            </li>)}</ul>}
      {ticket.diagnosed_at && <dl className={styles.facts}>
        <dt>Found</dt><dd>{ticket.findings}</dd>
        <dt>Recommended</dt><dd>{ticket.recommendation}</dd>
        <dt>Recorded</dt><dd>{formatDateTime(ticket.diagnosed_at)}</dd>
      </dl>}
    </section>

    <Estimates ticket={ticket} isOffice={isOffice} onChanged={refresh}
      onRaise={() => setDialog(specs.estimate)} allowed={allowed} />

    <WorkDone ticket={ticket} canWork={canWork} onChanged={refresh} />

    {ticket.replacements.length > 0 && <section className={styles.section}>
      <h2>Replacements</h2>
      <ul className={styles.results}>{ticket.replacements.map((row) =>
        <li key={row.id} className={styles.result}>
          <span><Reference>{row.old_asset_id}</Reference> replaced by{" "}
            <Reference>{row.new_asset_id}</Reference>
            <div className={styles.muted}>{row.reason}</div></span>
          <span className={styles.muted}>Old unit {row.disposition}
            {row.new_warranty ? " · cover moved across" : " · paid, no cover to move"}</span>
        </li>)}</ul>
    </section>}

    {ticket.confirmed_at && <section className={styles.section}>
      <h2>Closed</h2>
      <dl className={styles.facts}>
        <dt>Confirmed by</dt><dd>{ticket.confirmed_by_name}</dd>
        <dt>When</dt><dd>{formatDateTime(ticket.confirmed_at)}</dd>
      </dl>
    </section>}

    {canWork && <Photos ticket={ticket} onChanged={refresh} />}

    {dialog && <ActionDialog spec={dialog} onClose={() => setDialog(null)}
      onDone={() => { setDialog(null); refresh(); }} />}
  </>;
}

// ============================================================
// Sections
// ============================================================

function Equipment({ ticket, isManager, onChanged }: {
  ticket: Ticket; isManager: boolean; onChanged: () => void;
}) {
  const [reviewing, setReviewing] = useState<TicketAsset | null>(null);
  const columns: readonly Column<TicketAsset>[] = [
    {
      header: "Asset",
      render: (asset) => <>
        <Reference>{asset.asset_id}</Reference>
        <div className={styles.muted}>{asset.serial_number || "No serial printed"}</div>
      </>,
    },
    { header: "Item", render: (asset) => asset.product_name },
    {
      header: "Cover to",
      render: (asset) => asset.warranty
        ? <Link to={`/warranties/${asset.warranty}`}>
            {asset.last_covered_on ? formatDate(asset.last_covered_on) : asset.policy_name}
          </Link>
        : "No warranty",
    },
    {
      header: "Assessment",
      render: (asset) => <>
        <StatusBadge status={ASSESSMENTS[asset.assessment]} />
        {asset.review_reason && <div className={styles.muted}>{asset.review_reason}</div>}
      </>,
    },
  ];
  const needsReview = ticket.assets.filter((asset) => asset.assessment === "review");

  return <section className={styles.section}>
    <h2>Equipment and cover</h2>
    {ticket.claimed_complaint_at && needsReview.length > 0 && <p className={styles.notice}>
      The customer claims an earlier date, so coverage waits for a manager's review.
    </p>}
    <DataTable caption="Affected equipment" columns={columns} rows={ticket.assets}
      rowKey={(asset) => asset.id} />
    {isManager && ticket.allowed_actions.includes("review") && <div className={styles.actions}>
      {ticket.assets.map((asset) => <Button key={asset.id} onClick={() => setReviewing(asset)}>
        Review {asset.asset_id}
      </Button>)}
    </div>}
    {reviewing && <ReviewDialog ticket={ticket} asset={reviewing}
      onClose={() => setReviewing(null)} onDone={() => { setReviewing(null); onChanged(); }} />}
  </section>;
}

function ReviewDialog({ ticket, asset, onClose, onDone }: {
  ticket: Ticket; asset: TicketAsset; onClose: () => void; onDone: () => void;
}) {
  return <ActionDialog onClose={onClose} onDone={onDone} spec={{
    title: `Rule on ${asset.asset_id}`, confirm: "Record decision",
    fields: [
      { name: "assessment", label: "Decision", kind: "select", required: true, initial: "covered",
        options: [{ value: "covered", label: "Covered" }, { value: "not_covered", label: "Not covered" }] },
      { name: "reason", label: "Why", kind: "area", required: true },
    ],
    submit: (values) => reviewAsset(ticket, asset.id, values),
  }} />;
}

function Estimates({ ticket, isOffice, onChanged, onRaise, allowed }: {
  ticket: Ticket; isOffice: boolean; onChanged: () => void; onRaise: () => void;
  allowed: (action: string) => boolean;
}) {
  const [deciding, setDeciding] = useState<boolean | null>(null);
  const uncovered = ticket.assets.some((asset) => asset.assessment === "not_covered");
  if (!uncovered && ticket.estimates.length === 0) return null;

  const pending = ticket.estimates.some((estimate) => estimate.status === "pending");

  return <section className={styles.section}>
    <h2>Estimates</h2>
    {ticket.estimates.length === 0 &&
      <p className={styles.muted}>Uncovered work needs an approved estimate before it starts.</p>}
    {ticket.estimates.map((estimate) => <EstimateCard key={estimate.id} estimate={estimate} />)}

    {isOffice && <div className={styles.actions}>
      {allowed("estimate") && <Button onClick={onRaise}>Raise an estimate</Button>}
      {allowed("decide-estimate") && pending && <>
        <Button variant="primary" onClick={() => setDeciding(true)}>Customer approved</Button>
        <Button onClick={() => setDeciding(false)}>Customer declined</Button>
      </>}
    </div>}

    {deciding !== null && <ActionDialog onClose={() => setDeciding(null)}
      onDone={() => { setDeciding(null); onChanged(); }} spec={{
        title: deciding ? "Record the approval" : "Record the refusal",
        confirm: deciding ? "Record approval" : "Record refusal",
        fields: [{ name: "customer_name", label: "Who decided", required: true }],
        submit: (values) => ticketAction(ticket, "decide-estimate", {
          approved: deciding, customer_name: values.customer_name,
        }),
      }} />}
  </section>;
}

function EstimateCard({ estimate }: { estimate: RepairEstimate }) {
  return <div className={styles.result}>
    <span>
      Estimate {estimate.number}: {formatMoney(estimate.gross_incl_tax)} incl. GST
      <div className={styles.muted}>
        {estimate.lines.map((line) =>
          `${formatQuantity(line.quantity, line.unit)} ${line.description}`).join(", ")}
        {estimate.decided_by_name && ` · ${estimate.decided_by_name}`}
      </div>
    </span>
    <StatusBadge status={ESTIMATE_STATUSES[estimate.status]} />
  </div>;
}

function WorkDone({ ticket, canWork, onChanged }: {
  ticket: Ticket; canWork: boolean; onChanged: () => void;
}) {
  const [voiding, setVoiding] = useState<WorkLine | null>(null);
  const showCost = ticket.work_lines.some((line) => line.unit_cost !== undefined);

  const columns: Column<WorkLine>[] = [
    {
      header: "Item",
      render: (line) => <span className={line.voided_reason ? styles.voided : undefined}>
        {formatQuantity(line.quantity, line.unit)} {line.description}
      </span>,
    },
    {
      header: "Charged incl. GST", numeric: true,
      render: (line) => formatMoney(Number(line.charge_excl_tax) + Number(line.charge_tax)),
    },
  ];
  if (showCost) {
    columns.push({
      header: "Internal cost", numeric: true,
      render: (line) => formatMoney(Number(line.quantity) * Number(line.unit_cost ?? 0)),
    });
  }
  columns.push({
    header: "Invoice",
    render: (line) => line.voided_reason || line.invoice_reference || "Not billed yet",
  });
  if (canWork && ticket.allowed_actions.includes("void-line")) {
    columns.push({
      header: "",
      render: (line) => !line.voided_reason && !line.invoice &&
        <Button onClick={() => setVoiding(line)}>Void</Button>,
    });
  }

  return <section className={styles.section}>
    <h2>Work done</h2>
    {ticket.work_lines.length === 0
      ? <p className={styles.muted}>Nothing recorded yet.</p>
      : <DataTable caption="Work done" columns={columns} rows={ticket.work_lines}
          rowKey={(line) => line.id} />}

    {voiding && <ActionDialog onClose={() => setVoiding(null)}
      onDone={() => { setVoiding(null); onChanged(); }} spec={{
        title: `Void ${voiding.description}`, confirm: "Void line",
        fields: [{ name: "reason", label: "Why", kind: "area", required: true }],
        submit: (values) => ticketAction(ticket, "void-line", {
          line: voiding.id, reason: values.reason,
        }),
      }} />}
  </section>;
}

function Photos({ ticket, onChanged }: { ticket: Ticket; onChanged: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const mutation = useMutation({
    mutationFn: () => uploadTicketPhoto(ticket, file as File, caption),
    onSuccess: () => { setCaption(""); setFile(null); onChanged(); },
  });

  return <section className={styles.section}>
    <h2>Photos</h2>
    {ticket.photos.map((photo) => <div key={photo.id} className={styles.muted}>
      {photo.caption} · {formatDateTime(photo.uploaded_at)}
    </div>)}
    <div className={styles.form}>
      <FileField label="Photo" accept="image/jpeg,image/png" onChange={setFile} />
      <TextField label="Caption" value={caption} onChange={setCaption} />
      <Button onClick={() => mutation.mutate()}
        disabled={!file || !caption.trim() || mutation.isPending}>Add photo</Button>
      {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}
    </div>
  </section>;
}

// ============================================================
// The one dialog
// ============================================================

function ActionDialog({ spec, onClose, onDone }: {
  spec: ActionSpec; onClose: () => void; onDone: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(
    spec.fields.map((field) => [field.name, field.initial ?? ""])
  ));
  const set = (name: string) => (value: string) =>
    setValues((current) => ({ ...current, [name]: value }));

  const mutation = useMutation({ mutationFn: () => spec.submit(values), onSuccess: onDone });
  const complete = spec.fields.every((field) => !field.required || values[field.name]?.trim());

  return <ConfirmDialog title={spec.title} confirmLabel={spec.confirm} pending={mutation.isPending}
    error={mutation.isError ? describeError(mutation.error)
      : !complete ? "Fill in every required field." : null}
    onConfirm={() => { if (complete) mutation.mutate(); }} onCancel={onClose}>
    <div className={styles.form}>
      {spec.note && <p className={styles.muted}>{spec.note}</p>}
      {spec.fields.map((field) => {
        const shared = { label: field.label, required: field.required, value: values[field.name],
                         onChange: set(field.name) };
        if (field.kind === "area") return <TextAreaField key={field.name} {...shared} />;
        if (field.kind === "select") {
          return <SelectField key={field.name} {...shared} placeholder="Choose"
            options={field.options ?? []} />;
        }
        const isTime = field.name === "starts_at" || field.name === "ends_at";
        return <TextField key={field.name} {...shared} type={isTime ? "datetime-local" : "text"} />;
      })}
    </div>
  </ConfirmDialog>;
}
