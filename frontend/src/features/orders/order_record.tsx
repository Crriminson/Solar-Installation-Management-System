/*
  One order: the terms, what has been invoiced, and what has been paid.

  The dispatch banner is the point of this screen. Warehouse staff need
  one unambiguous answer to "can this go out?", and that answer is the
  server's, computed from cleared money only.

  Confirming the order sent it to the warehouse and the diary (spec.md
  F07), so this screen says where it went and links to both. An order
  confirmed before that was automatic can be sent on from here.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { describeError } from "../../api/client";
import Button, { ButtonLink } from "../../components/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type Column } from "../../components/DataTable";
import { SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { ErrorMessage, LoadingRecord } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { useToast } from "../../components/ToastContext";
import { businessToday, formatDate, formatDateTime, formatMoney } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import JobCostSection from "../costing/job_cost_section";
import { openFulfilment } from "../fulfilment/api";
import { FULFILMENT_STATUSES } from "../fulfilment/status";
import { openInstallationJob } from "../scheduling/api";
import { JOB_STATUSES } from "../scheduling/status";
import OrderWarrantiesSection from "../warranties/order_warranties";
import { allocatePayment, cancelOrder, clearPayment, fetchOrder, issueBalanceInvoice,
         recordPayment, reversePayment } from "./api";
import { INVOICE_KINDS, ORDER_STATUSES, PAYMENT_METHODS, PAYMENT_STATUSES } from "./status";
import type { Invoice, Order, Payment } from "./types";
import styles from "./orders.module.css";

export default function OrderRecord() {
  const { orderId = "" } = useParams();
  const result = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => fetchOrder(orderId),
  });

  if (result.isPending) return <LoadingRecord label="Loading order…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <OrderDetails order={result.data} />;
}

function OrderDetails({ order }: { order: Order }) {
  const user = useStaffUser();
  const canTakeMoney = hasRole(user, "finance");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const queryClient = useQueryClient();
  const confirm = useToast();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["orders"] });

  const cancellation = useMutation({
    mutationFn: () => cancelOrder(order, reason),
    onSuccess: () => {
      setCancelling(false);
      confirm(`Order ${order.reference} cancelled`);
      refresh();
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["fulfilments"] });
    },
  });
  const balance = useMutation({
    mutationFn: () => issueBalanceInvoice(order),
    onSuccess: refresh,
  });

  const hasBalanceInvoice = order.invoices.some((invoice) => invoice.kind === "balance");
  const open = order.status === "confirmed";
  const delivered = order.status === "delivered" || order.status === "completed";

  const invoiceColumns: readonly Column<Invoice>[] = [
    { header: "Invoice", render: (invoice) => <Reference>{invoice.reference}</Reference> },
    { header: "For", render: (invoice) => INVOICE_KINDS[invoice.kind] ?? invoice.kind },
    { header: "Amount", numeric: true, render: (invoice) => formatMoney(invoice.amount) },
    { header: "Paid", numeric: true, render: (invoice) => formatMoney(invoice.paid_amount) },
    { header: "Outstanding", numeric: true, render: (invoice) => formatMoney(invoice.outstanding) },
    { header: "Issued", render: (invoice) => formatDate(invoice.issued_at) },
  ];

  return <>
    <PageHeader back={{ to: "/orders", label: "Orders" }}
      title={<Reference>{order.reference}</Reference>}
      subtitle={`${order.customer_name} · from ${order.quotation_reference}`}
      actions={open && <ButtonLink to={`/quotations/${order.quotation}`}>View quotation</ButtonLink>}
      status={<StatusBadge status={ORDER_STATUSES[order.status]} />} />

    <p className={order.dispatch_allowed ? styles.cleared : styles.waitingBanner}>
      {order.dispatch_allowed
        ? "Money cleared. Dispatch may proceed once stock is ready."
        : `Dispatch is held until ${formatMoney(order.advance_payable)} has cleared. ` +
          `${formatMoney(order.cleared_total)} has cleared so far.`}
    </p>

    <section className={styles.section}>
      <h2>Terms</h2>
      <dl className={styles.facts}>
        <dt>Order value incl. GST</dt><dd>{formatMoney(order.gross_payable)}</dd>
        <dt>Payment plan</dt>
        <dd>{order.payment_plan === "advance"
          ? `${formatMoney(order.advance_payable)} advance, remainder on delivery`
          : "Full payment before dispatch"}</dd>
        <dt>Cleared so far</dt><dd>{formatMoney(order.cleared_total)}</dd>
        <dt>Outstanding</dt><dd>{formatMoney(order.outstanding)}</dd>
        <dt>Balance due</dt>
        <dd>{order.balance_due_on ? formatDate(order.balance_due_on) : "On delivery completion"}</dd>
        <dt>Confirmed</dt><dd>{formatDateTime(order.confirmed_at)}</dd>
        {order.cancelled_reason && <><dt>Cancelled because</dt><dd>{order.cancelled_reason}</dd></>}
      </dl>
    </section>

    <HandoffSection order={order} open={open} />

    <section className={styles.section}>
      <h2>Invoices</h2>
      <DataTable caption="Invoices" columns={invoiceColumns} rows={order.invoices}
        rowKey={(invoice) => invoice.id} />
      {canTakeMoney && open && order.payment_plan === "advance" && !hasBalanceInvoice &&
        <div className={styles.actions}>
          <Button onClick={() => balance.mutate()} disabled={balance.isPending}>
            Raise balance invoice
          </Button>
          {balance.isError && <span className={styles.error}>{describeError(balance.error)}</span>}
        </div>}
    </section>

    <PaymentSection order={order} canTakeMoney={canTakeMoney} onChanged={refresh} />

    {delivered && <OrderWarrantiesSection orderId={order.id} />}

    {user.can_view_costs && <JobCostSection orderId={order.id} />}

    {open && <div className={styles.actions}>
      <Button onClick={() => setCancelling(true)}>Cancel order</Button>
    </div>}

    {cancelling && <ConfirmDialog title={`Cancel ${order.reference}?`}
      confirmLabel="Cancel order" pending={cancellation.isPending}
      error={cancellation.isError ? describeError(cancellation.error) : null}
      onConfirm={() => cancellation.mutate()} onCancel={() => setCancelling(false)}>
      <p>Reserved stock goes back on the shelf and the installation is called off.
        Money already taken is returned as a refund, not erased.</p>
      <TextAreaField label="Why is this order cancelled?" required value={reason}
        onChange={setReason} />
    </ConfirmDialog>}
  </>;
}

// ============================================================
// Where the order went
// ============================================================

function HandoffSection({ order, open }: { order: Order; open: boolean }) {
  const user = useStaffUser();
  const queryClient = useQueryClient();
  const confirm = useToast();
  const isOperations = hasRole(user, "operations_manager");
  const canPack = isOperations || hasRole(user, "warehouse");

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["orders"] });
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
    queryClient.invalidateQueries({ queryKey: ["fulfilments"] });
  };
  const packing = useMutation({
    mutationFn: () => openFulfilment(order.id),
    onSuccess: () => { confirm(`Packing list opened for ${order.reference}`); refresh(); },
  });
  const installation = useMutation({
    mutationFn: () => openInstallationJob(order.id),
    onSuccess: () => { confirm(`Installation for ${order.reference} awaits scheduling`); refresh(); },
  });

  const { fulfilment, installation: job } = order;

  return <section className={styles.section}>
    <h2>Delivery and installation</h2>
    <dl className={styles.facts}>
      <dt>Packing</dt>
      <dd>
        {fulfilment
          ? <>
              <StatusBadge status={FULFILMENT_STATUSES[fulfilment.status]} />
              {fulfilment.status === "blocked" &&
                <div className={styles.muted}>{fulfilment.blocked_reason}</div>}
            </>
          : "No packing list"}
      </dd>
      <dt>Installation</dt>
      <dd>
        {job
          ? <>
              <StatusBadge status={JOB_STATUSES[job.status]} />
              <div className={styles.muted}>
                {job.starts_at ? formatDateTime(job.starts_at) : "Not booked yet"}
              </div>
            </>
          : "No installation job"}
      </dd>
    </dl>

    <div className={styles.actions}>
      {fulfilment && <ButtonLink to={`/packing/${fulfilment.id}`}>Packing list</ButtonLink>}
      {job && (job.status === "awaiting_scheduling" && isOperations
        ? <ButtonLink variant="primary" to={`/schedule/${job.id}`}>Book the installation</ButtonLink>
        : <ButtonLink to={`/schedule/${job.id}`}>Installation job</ButtonLink>)}

      {/* For an order confirmed before confirmation did these itself. */}
      {open && !fulfilment && canPack &&
        <Button loading={packing.isPending} onClick={() => packing.mutate()}>
          Open packing list
        </Button>}
      {open && !job && isOperations &&
        <Button loading={installation.isPending} onClick={() => installation.mutate()}>
          Create installation job
        </Button>}
    </div>
    {(packing.isError || installation.isError) &&
      <p className={styles.error}>{describeError(packing.error ?? installation.error)}</p>}
  </section>;
}

// ============================================================
// Payments
// ============================================================

function PaymentSection({ order, canTakeMoney, onChanged }: {
  order: Order; canTakeMoney: boolean; onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);

  const columns: readonly Column<Payment>[] = [
    { header: "Paid on", render: (payment) => formatDate(payment.paid_on) },
    {
      header: "Amount", numeric: true,
      render: (payment) => <>{payment.kind === "refund" ? "−" : ""}{formatMoney(payment.amount)}</>,
    },
    { header: "Method", render: (payment) => <>{payment.method.replace("_", " ")}
      {payment.external_reference && <div className={styles.muted}>{payment.external_reference}</div>}</> },
    { header: "Status", render: (payment) => <StatusBadge status={PAYMENT_STATUSES[payment.status]} /> },
    { header: "Unallocated", numeric: true, render: (payment) => formatMoney(payment.unallocated) },
    { header: "Recorded by", render: (payment) => payment.recorded_by_name || "—" },
  ];

  return <section className={styles.section}>
    <h2>Payments</h2>
    {order.payments.length === 0
      ? <p className={styles.muted}>Nothing recorded yet.</p>
      : <DataTable caption="Payments" columns={columns} rows={order.payments}
          rowKey={(payment) => payment.id} />}

    {canTakeMoney && <>
      <div className={styles.actions}>
        <Button variant="primary" onClick={() => setAdding(true)}
          disabled={order.status === "cancelled"}>Record payment</Button>
      </div>
      {order.payments.map((payment) =>
        <PaymentActions key={payment.id} order={order} payment={payment} onChanged={onChanged} />)}
      {adding && <PaymentForm order={order} onClose={() => setAdding(false)}
        onSaved={() => { setAdding(false); onChanged(); }} />}
    </>}
  </section>;
}

function PaymentActions({ order, payment, onChanged }: {
  order: Order; payment: Payment; onChanged: () => void;
}) {
  const [reversing, setReversing] = useState(false);
  const [reason, setReason] = useState("");
  const [allocatingTo, setAllocatingTo] = useState("");
  const [amount, setAmount] = useState("");

  /* Money moving is worth confirming out loud. The row already shows
     the new state; the toast says the request landed. */
  const confirm = useToast();

  const clearing = useMutation({
    mutationFn: () => clearPayment(payment),
    onSuccess: () => { confirm(`Payment of ${formatMoney(payment.amount)} cleared`); onChanged(); },
  });
  const reversal = useMutation({
    mutationFn: () => reversePayment(payment, reason),
    onSuccess: () => {
      setReversing(false);
      confirm(`Payment of ${formatMoney(payment.amount)} reversed`);
      onChanged();
    },
  });
  const allocation = useMutation({
    mutationFn: () => allocatePayment(payment, Number(allocatingTo), amount),
    onSuccess: () => {
      setAllocatingTo("");
      setAmount("");
      confirm("Allocation recorded");
      onChanged();
    },
  });

  if (payment.status === "reversed") return null;

  const unsettled = order.invoices.filter((invoice) => !invoice.settled);
  const canAllocate = payment.status === "cleared"
    && payment.kind === "receipt"
    && Number(payment.unallocated) > 0
    && unsettled.length > 0;

  return <div className={styles.paymentRow}>
    <span className={styles.muted}>
      {formatMoney(payment.amount)} · {formatDate(payment.paid_on)}
    </span>

    {payment.status === "pending" &&
      <Button onClick={() => clearing.mutate()} disabled={clearing.isPending}>
        Mark cleared
      </Button>}

    {canAllocate && <>
      <SelectField label="Allocate to" value={allocatingTo}
        options={[{ value: "", label: "Choose an invoice" },
          ...unsettled.map((invoice) => ({
            value: String(invoice.id),
            label: `${invoice.reference} · ${formatMoney(invoice.outstanding)} outstanding`,
          }))]}
        onChange={setAllocatingTo} />
      <TextField label="Amount" value={amount} onChange={setAmount} inputMode="decimal" />
      <Button onClick={() => allocation.mutate()}
        disabled={!allocatingTo || !amount || allocation.isPending}>Allocate</Button>
    </>}

    <Button onClick={() => setReversing(true)}>Reverse</Button>

    {(clearing.isError || allocation.isError) &&
      <span className={styles.error}>
        {describeError(clearing.error ?? allocation.error)}
      </span>}

    {reversing && <ConfirmDialog title={`Reverse ${formatMoney(payment.amount)}?`}
      confirmLabel="Reverse payment" pending={reversal.isPending}
      error={reversal.isError ? describeError(reversal.error) : null}
      onConfirm={() => reversal.mutate()} onCancel={() => setReversing(false)}>
      <p>The payment stays on the ledger, marked reversed, and anything it settled
        is released. Use this for a mis-entry, not for money going back to the
        customer — that is a refund.</p>
      <TextAreaField label="Why is this being reversed?" required value={reason}
        onChange={setReason} />
    </ConfirmDialog>}
  </div>;
}

function PaymentForm({ order, onClose, onSaved }: {
  order: Order; onClose: () => void; onSaved: () => void;
}) {
  const [amount, setAmount] = useState(order.outstanding);
  const [method, setMethod] = useState("upi");
  const [externalReference, setExternalReference] = useState("");
  const [kind, setKind] = useState("receipt");
  const [status, setStatus] = useState("cleared");
  const [paidOn, setPaidOn] = useState(businessToday());
  const confirm = useToast();

  /* The amount comes from the saved payment, not the input, so the
     toast repeats what the server recorded. */
  const mutation = useMutation({
    mutationFn: () => recordPayment(order.id, {
      kind, amount, method, external_reference: externalReference,
      status, paid_on: paidOn,
    }),
    onSuccess: (payment) => {
      const what = payment.kind === "refund" ? "Refund" : "Payment";
      confirm(`${what} of ${formatMoney(payment.amount)} recorded on ${order.reference}`);
      onSaved();
    },
  });

  return <ConfirmDialog title={`Record payment on ${order.reference}`}
    confirmLabel="Record payment" pending={mutation.isPending}
    error={mutation.isError ? describeError(mutation.error) : null}
    onConfirm={() => mutation.mutate()} onCancel={onClose}>
    <div className={styles.form}>
      <SelectField label="Direction" value={kind} options={[
        { value: "receipt", label: "Received from customer" },
        { value: "refund", label: "Returned to customer" },
      ]} onChange={setKind} />
      <TextField label="Amount" required value={amount} onChange={setAmount}
        inputMode="decimal" />
      <SelectField label="Method" value={method} options={PAYMENT_METHODS}
        onChange={setMethod} />
      <TextField label="Bank, UPI or cheque reference" value={externalReference}
        onChange={setExternalReference}
        hint="Recorded once. The same reference cannot be banked twice." />
      <TextField label="Date the money moved" type="date" required value={paidOn}
        onChange={setPaidOn} />
      <SelectField label="Has it arrived?" value={status} options={[
        { value: "cleared", label: "Yes, cleared" },
        { value: "pending", label: "Not yet — pending" },
      ]} onChange={setStatus} />
    </div>
  </ConfirmDialog>;
}
