/*
  What this job cost, on the order record (F14).

  Laid out as the sum it is, so operational margin can be checked by eye.
  Service cost sits below that line on purpose: spec.md F15 keeps it
  outside operational margin. Only shown to those who may see cost, and
  the server refuses everyone else regardless.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import { TextField } from "../../components/Field";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { businessToday, formatDate, formatMoney } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchExpenses, fetchJobCost, recordExpense, reverseExpense, type Expense } from "./api";
import ReasonDialog from "./reason_dialog";
import styles from "./costing.module.css";

export default function JobCostSection({ orderId }: { orderId: number }) {
  const user = useStaffUser();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["job-cost", orderId] });
  const canMoveMoney = hasRole(user, "finance");

  const cost = useQuery({
    queryKey: ["job-cost", orderId, "figures"], queryFn: () => fetchJobCost(orderId),
  });

  return <section className={styles.section}>
    <h2>Job cost</h2>
    {cost.isPending && <LoadingMessage label="Working out the job's cost…" />}
    {cost.isError && <ErrorMessage error={cost.error} onRetry={cost.refetch} />}
    {cost.data && <dl className={styles.facts}>
      <dt>Net revenue excl. GST</dt><dd>{formatMoney(cost.data.net_revenue_excl_tax)}</dd>
      <dt>Equipment issued</dt><dd>−{formatMoney(cost.data.equipment_cost)}</dd>
      <dt>Labour ({Number(cost.data.labour_hours)} h)</dt><dd>−{formatMoney(cost.data.labour_cost)}</dd>
      <dt>Project expenses</dt><dd>−{formatMoney(cost.data.project_expenses)}</dd>
      <dt className={styles.total}>Operational margin</dt>
      <dd className={styles.total}>{formatMoney(cost.data.operational_margin)}</dd>
      <dt>Quoted margin</dt><dd>{formatMoney(cost.data.quoted_margin)}</dd>
      <dt>Warranty and service cost</dt><dd>{formatMoney(cost.data.service_cost)}</dd>
      <dt>Repair revenue excl. GST</dt><dd>{formatMoney(cost.data.repair_revenue_excl_tax)}</dd>
      <dt>Lifetime job contribution</dt><dd>{formatMoney(cost.data.lifetime_contribution)}</dd>
    </dl>}

    <Expenses orderId={orderId} canMoveMoney={canMoveMoney} onChanged={refresh} />
  </section>;
}

function Expenses({ orderId, canMoveMoney, onChanged }: {
  orderId: number; canMoveMoney: boolean; onChanged: () => void;
}) {
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [incurredOn, setIncurredOn] = useState(businessToday());
  const [reversing, setReversing] = useState<Expense | null>(null);

  const expenses = useQuery({
    queryKey: ["job-cost", orderId, "expenses"], queryFn: () => fetchExpenses(orderId),
  });
  const mutation = useMutation({
    mutationFn: () => recordExpense({
      order: orderId, description, amount_excl_tax: amount, incurred_on: incurredOn,
    }),
    onSuccess: () => { setDescription(""); setAmount(""); onChanged(); },
  });

  const columns: Column<Expense>[] = [
    { header: "On", render: (row) => formatDate(row.incurred_on) },
    {
      header: "Expense",
      render: (row) => <span className={row.is_reversed ? styles.reversed : undefined}>
        {row.description}
      </span>,
    },
    { header: "Excl. GST", numeric: true, render: (row) => formatMoney(row.amount_excl_tax) },
  ];
  if (canMoveMoney) {
    columns.push({
      header: "",
      render: (row) => row.is_reversed ? row.reversed_reason
        : <Button onClick={() => setReversing(row)}>Reverse</Button>,
    });
  }

  return <>
    <h2>Project expenses</h2>
    {expenses.data && expenses.data.count > 0
      ? <DataTable caption="Project expenses" columns={columns} rows={expenses.data.results}
          rowKey={(row) => row.id} />
      : <p className={styles.muted}>None recorded. Stock is costed when issued, not here.</p>}

    {canMoveMoney && <div className={styles.actions}>
      <TextField label="Description" value={description} onChange={setDescription} />
      <TextField label="Amount excl. GST" inputMode="decimal" value={amount} onChange={setAmount} />
      <TextField label="Incurred on" type="date" value={incurredOn} onChange={setIncurredOn} />
      <Button onClick={() => mutation.mutate()}
        disabled={!description.trim() || !amount || mutation.isPending}>Add expense</Button>
    </div>}
    {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}

    {reversing && <ReasonDialog title={`Reverse ${reversing.description}?`}
      confirmation={`${reversing.description} reversed`}
      onSubmit={(reason) => reverseExpense(reversing.id, reason)}
      onClose={() => setReversing(null)}
      onDone={() => { setReversing(null); onChanged(); }} />}
  </>;
}
