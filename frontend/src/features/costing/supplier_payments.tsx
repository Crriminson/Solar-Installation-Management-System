/*
  What a supplier billed and what has been paid (F14), on a purchase.

  The status on the purchase follows these rows, so nobody sets it by
  hand and it cannot disagree with the money.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import { TextField } from "../../components/Field";
import { businessToday, formatDate, formatMoney } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchSupplierPayments, paySupplier, recordSupplierInvoice, reverseSupplierPayment,
         type SupplierPayment } from "./api";
import ReasonDialog from "./reason_dialog";
import styles from "./costing.module.css";

export default function SupplierPayments({ purchaseId, hasInvoice }: {
  purchaseId: number; hasInvoice: boolean;
}) {
  const user = useStaffUser();
  const queryClient = useQueryClient();
  const canMoveMoney = hasRole(user, "finance");
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["supplier-payments", purchaseId] });
    queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
    queryClient.invalidateQueries({ queryKey: ["purchase-order"] });
    queryClient.invalidateQueries({ queryKey: ["purchases"] });
  };

  const [reference, setReference] = useState("");
  const [amount, setAmount] = useState("");
  const [paidOn, setPaidOn] = useState(businessToday());
  const [reversing, setReversing] = useState<SupplierPayment | null>(null);

  const payments = useQuery({
    queryKey: ["supplier-payments", purchaseId],
    queryFn: () => fetchSupplierPayments(purchaseId),
  });
  const invoice = useMutation({
    mutationFn: () => recordSupplierInvoice(purchaseId, reference, amount),
    onSuccess: () => { setReference(""); setAmount(""); refresh(); },
  });
  const payment = useMutation({
    mutationFn: () => paySupplier({
      purchase_order: purchaseId, amount, paid_on: paidOn, reference,
    }),
    onSuccess: () => { setReference(""); setAmount(""); refresh(); },
  });

  const columns: Column<SupplierPayment>[] = [
    { header: "Paid on", render: (row) => formatDate(row.paid_on) },
    {
      header: "Amount incl. GST", numeric: true,
      render: (row) => <span className={row.is_reversed ? styles.reversed : undefined}>
        {formatMoney(row.amount)}
      </span>,
    },
    { header: "Reference", render: (row) => row.reference || "—" },
  ];
  if (canMoveMoney) {
    columns.push({
      header: "",
      render: (row) => row.is_reversed ? row.reversed_reason
        : <Button onClick={() => setReversing(row)}>Reverse</Button>,
    });
  }

  const error = invoice.error ?? payment.error;

  return <section className={styles.section}>
    <h2>Supplier payments</h2>
    {payments.data && payments.data.count > 0
      ? <DataTable caption="Supplier payments" columns={columns} rows={payments.data.results}
          rowKey={(row) => row.id} />
      : <p className={styles.muted}>Nothing paid yet.</p>}

    {canMoveMoney && <div className={styles.actions}>
      <TextField label={hasInvoice ? "Payment reference" : "Supplier invoice number"}
        value={reference} onChange={setReference} />
      <TextField label="Amount incl. GST" inputMode="decimal" value={amount} onChange={setAmount} />
      {hasInvoice
        ? <>
            <TextField label="Paid on" type="date" value={paidOn} onChange={setPaidOn} />
            <Button onClick={() => payment.mutate()} disabled={!amount || payment.isPending}>
              Record payment
            </Button>
          </>
        : <Button onClick={() => invoice.mutate()}
            disabled={!reference.trim() || !amount || invoice.isPending}>Record invoice</Button>}
    </div>}
    {error && <p className={styles.error}>{describeError(error)}</p>}

    {reversing && <ReasonDialog title={`Reverse ${formatMoney(reversing.amount)}?`}
      onSubmit={(reason) => reverseSupplierPayment(reversing.id, reason)}
      onClose={() => setReversing(null)}
      onDone={() => { setReversing(null); refresh(); }} />}
  </section>;
}
