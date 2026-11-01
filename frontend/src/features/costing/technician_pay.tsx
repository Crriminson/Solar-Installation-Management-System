/*
  Technician pay (F14): an accrual ledger, not payroll (D025).

  Time entries accrue a payable at the rate that applied. Finance records
  payments against that balance, and the server refuses to pay more than
  has accrued. No payslips, deductions or tax, by design.
*/

import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import DataTable, { type Column } from "../../components/DataTable";
import Pagination from "../../components/Pagination";
import { TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { businessToday, formatDate, formatMoney, formatQuantity } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchTechnicianPayments, fetchTechnicianSummaries, payTechnician, reverseTechnicianPayment,
         setRate, type TechnicianPayment, type TechnicianSummary } from "./api";
import ReasonDialog from "./reason_dialog";
import styles from "./costing.module.css";

export default function TechnicianPay() {
  const user = useStaffUser();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["technician-pay"] });
  const canMoveMoney = hasRole(user, "finance");

  const [paying, setPaying] = useState<TechnicianSummary | null>(null);
  const [rating, setRating] = useState<TechnicianSummary | null>(null);
  const [reversing, setReversing] = useState<TechnicianPayment | null>(null);
  const [page, setPage] = useState(1);

  const summaries = useQuery({
    queryKey: ["technician-pay", "summaries"], queryFn: fetchTechnicianSummaries,
  });
  const payments = useQuery({
    queryKey: ["technician-pay", "payments", page], queryFn: () => fetchTechnicianPayments(page),
    placeholderData: keepPreviousData,
  });

  const columns: Column<TechnicianSummary>[] = [
    { header: "Technician", render: (row) => row.name },
    {
      header: "Rate per hour",
      render: (row) => row.current_rate ? formatMoney(row.current_rate)
        : <span className={styles.error}>No rate set</span>,
    },
    { header: "Hours", numeric: true, render: (row) => formatQuantity(row.hours, "h") },
    { header: "Accrued", numeric: true, render: (row) => formatMoney(row.accrued) },
    { header: "Paid", numeric: true, render: (row) => formatMoney(row.paid) },
    { header: "Outstanding", numeric: true, render: (row) => formatMoney(row.outstanding) },
  ];
  if (canMoveMoney) {
    columns.push({
      header: "",
      render: (row) => <div className={styles.actions}>
        <Button onClick={() => setPaying(row)} disabled={Number(row.outstanding) <= 0}>Pay</Button>
        <Button onClick={() => setRating(row)}>Set rate</Button>
      </div>,
    });
  }

  const paymentColumns: Column<TechnicianPayment>[] = [
    { header: "Paid on", render: (row) => formatDate(row.paid_on) },
    { header: "Technician", render: (row) => row.technician_name },
    {
      header: "Amount", numeric: true,
      render: (row) => <span className={row.is_reversed ? styles.reversed : undefined}>
        {formatMoney(row.amount)}
      </span>,
    },
    { header: "Reference", render: (row) => row.reference || "—" },
  ];
  if (canMoveMoney) {
    paymentColumns.push({
      header: "",
      render: (row) => row.is_reversed ? row.reversed_reason
        : <Button onClick={() => setReversing(row)}>Reverse</Button>,
    });
  }

  if (summaries.isPending) return <LoadingMessage label="Loading technician balances…" />;
  if (summaries.isError) {
    return <ErrorMessage error={summaries.error} onRetry={summaries.refetch} />;
  }

  return <>
    <PageHeader title="Technician pay"
      subtitle="Hours accrue a payable at the rate that applied. Not payroll." />

    {summaries.data.length === 0
      ? <EmptyMessage>No technicians yet.</EmptyMessage>
      : <DataTable caption="Technician balances" columns={columns} rows={summaries.data}
          rowKey={(row) => row.technician} />}

    <section className={styles.section}>
      <h2>Payments</h2>
      {payments.data && payments.data.count > 0
        ? <>
            <DataTable caption="Payments" columns={paymentColumns} rows={payments.data.results}
              rowKey={(row) => row.id} />
            <Pagination page={page} count={payments.data.count} onChange={setPage} />
          </>
        : <p className={styles.muted}>Nothing paid yet.</p>}
    </section>

    {paying && <PayDialog summary={paying} onClose={() => setPaying(null)}
      onDone={() => { setPaying(null); refresh(); }} />}
    {rating && <RateDialog summary={rating} onClose={() => setRating(null)}
      onDone={() => { setRating(null); refresh(); }} />}
    {reversing && <ReasonDialog title={`Reverse ${formatMoney(reversing.amount)}?`}
      confirmation={`Payment of ${formatMoney(reversing.amount)} to ${reversing.technician_name} reversed`}
      onSubmit={(reason) => reverseTechnicianPayment(reversing.id, reason)}
      onClose={() => setReversing(null)}
      onDone={() => { setReversing(null); refresh(); }} />}
  </>;
}

function PayDialog({ summary, onClose, onDone }: {
  summary: TechnicianSummary; onClose: () => void; onDone: () => void;
}) {
  const [amount, setAmount] = useState(summary.outstanding);
  const [paidOn, setPaidOn] = useState(businessToday());
  const [reference, setReference] = useState("");
  const mutation = useMutation({
    mutationFn: () => payTechnician({
      technician: summary.technician, amount, paid_on: paidOn, reference,
    }),
    onSuccess: onDone,
  });

  return <ConfirmDialog title={`Pay ${summary.name}`} confirmLabel="Record payment"
    pending={mutation.isPending}
    error={mutation.isError ? describeError(mutation.error) : null}
    onConfirm={() => mutation.mutate()} onCancel={onClose}>
    <div className={styles.form}>
      <p className={styles.muted}>{formatMoney(summary.outstanding)} has accrued and is unpaid.</p>
      <TextField label="Amount" required inputMode="decimal" value={amount} onChange={setAmount} />
      <TextField label="Paid on" type="date" required value={paidOn} onChange={setPaidOn} />
      <TextField label="Reference" value={reference} onChange={setReference} />
    </div>
  </ConfirmDialog>;
}

function RateDialog({ summary, onClose, onDone }: {
  summary: TechnicianSummary; onClose: () => void; onDone: () => void;
}) {
  const [rate, setRateValue] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(businessToday());
  const mutation = useMutation({
    mutationFn: () => setRate({
      technician: summary.technician, rate_per_hour: rate, effective_from: effectiveFrom,
    }),
    onSuccess: onDone,
  });

  return <ConfirmDialog title={`Set a rate for ${summary.name}`} confirmLabel="Set rate"
    pending={mutation.isPending}
    error={mutation.isError ? describeError(mutation.error) : null}
    onConfirm={() => mutation.mutate()} onCancel={onClose}>
    <div className={styles.form}>
      <p className={styles.muted}>Past hours keep the rate they were recorded at.</p>
      <TextField label="Rate per hour" required inputMode="decimal" value={rate}
        onChange={setRateValue} />
      <TextField label="From" type="date" required value={effectiveFrom}
        onChange={setEffectiveFrom} />
    </div>
  </ConfirmDialog>;
}
