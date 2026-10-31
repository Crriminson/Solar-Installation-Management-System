/*
  One order: the terms, what has been invoiced, and what has been paid.

  The dispatch banner is the point of this screen. Warehouse staff need
  one unambiguous answer to "can this go out?", and that answer is the
  server's, computed from cleared money only.
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
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { businessToday, formatDate, formatDateTime, formatMoney } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
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

  if (result.isPending) return <LoadingMessage label="Loading order…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <OrderDetails order={result.data} />;
}

function OrderDetails({ order }: { order: Order }) {
  const user = useStaffUser();
  const canTakeMoney = hasRole(user, "finance");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["orders"] });

  const cancellation = useMutation({
    mutationFn: () => cancelOrder(order, reason),
    onSuccess: () => { setCancelling(false); refresh(); },
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
      actions={open && <ButtonLink to={`/quotations/${order.quotation}`}>View quotation</ButtonLink>}>
      <StatusBadge status={ORDER_STATUSES[order.status]} />
    </PageHeader>

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

    {open && <div className={styles.actions}>
      <Button onClick={() => setCancelling(true)}>Cancel order</Button>
    </div>}

    {cancelling && <ConfirmDialog title={`Cancel ${order.reference}?`}
      confirmLabel="Cancel order" pending={cancellation.isPending}
      error={cancellation.isError ? describeError(cancellation.error) : null}
      onConfirm={() => cancellation.mutate()} onCancel={() => setCancelling(false)}>
      <p>Money already taken is returned as a refund, not erased.</p>
      <TextAreaField label="Why is this order cancelled?" required value={reason}
        onChange={setReason} />
    </ConfirmDialog>}
  </>;
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

  const clearing = useMutation({ mutationFn: () => clearPayment(payment), onSuccess: onChanged });
  const reversal = useMutation({
    mutationFn: () => reversePayment(payment, reason),
    onSuccess: () => { setReversing(false); onChanged(); },
  });
  const allocation = useMutation({
    mutationFn: () => allocatePayment(payment, Number(allocatingTo), amount),
    onSuccess: () => { setAllocatingTo(""); setAmount(""); onChanged(); },
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

  const mutation = useMutation({
    mutationFn: () => recordPayment(order.id, {
      kind, amount, method, external_reference: externalReference,
      status, paid_on: paidOn,
    }),
    onSuccess: onSaved,
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
