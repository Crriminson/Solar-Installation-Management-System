/*
  Hours on one visit (F14), on the job record.

  A technician records their own day. Amounts appear only when the
  server sends them, and it does not send a rate to the technician.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import { TextField } from "../../components/Field";
import { ErrorMessage } from "../../components/StateMessage";
import { businessToday, formatDate, formatMoney, formatQuantity } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import { fetchTime, recordTime, reverseTime, type TimeEntry } from "./api";
import ReasonDialog from "./reason_dialog";
import styles from "./costing.module.css";

export default function TimeSection({ jobId, crew }: { jobId: number; crew: number[] }) {
  const user = useStaffUser();
  const queryClient = useQueryClient();
  const queryKey = ["job-time", jobId];
  const refresh = () => queryClient.invalidateQueries({ queryKey });

  const [hours, setHours] = useState("");
  const [workDate, setWorkDate] = useState(businessToday());
  const [reversing, setReversing] = useState<TimeEntry | null>(null);

  const entries = useQuery({ queryKey, queryFn: () => fetchTime(jobId) });
  const mutation = useMutation({
    mutationFn: () => recordTime({ job: jobId, hours, work_date: workDate }),
    onSuccess: () => { setHours(""); refresh(); },
  });

  const onCrew = crew.includes(user.id);
  const canReverse = hasRole(user, "finance");

  const columns: Column<TimeEntry>[] = [
    { header: "Day", render: (row) => formatDate(row.work_date) },
    { header: "Who", render: (row) => row.technician_name },
    {
      header: "Hours", numeric: true,
      render: (row) => <span className={row.is_reversed ? styles.reversed : undefined}>
        {formatQuantity(row.hours, "h")}
      </span>,
    },
  ];
  if (user.can_view_costs) {
    columns.push({
      header: "Cost", numeric: true,
      render: (row) => row.cost_amount ? formatMoney(row.cost_amount) : "—",
    });
  }
  if (canReverse) {
    columns.push({
      header: "",
      render: (row) => row.is_reversed ? row.reversed_reason
        : <Button onClick={() => setReversing(row)}>Reverse</Button>,
    });
  }

  return <section className={styles.section}>
    <h2>Hours</h2>
    {entries.isError && <ErrorMessage error={entries.error} onRetry={entries.refetch} />}
    {entries.data && entries.data.count > 0
      ? <DataTable caption="Hours on this job" columns={columns} rows={entries.data.results}
          rowKey={(row) => row.id} />
      : <p className={styles.muted}>No hours recorded yet.</p>}

    {onCrew && <div className={styles.actions}>
      <TextField label="Hours worked" inputMode="decimal" unit="h" value={hours} onChange={setHours} />
      <TextField label="Day" type="date" value={workDate} onChange={setWorkDate} />
      <Button onClick={() => mutation.mutate()} disabled={!hours || mutation.isPending}>
        Record hours
      </Button>
    </div>}
    {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}

    {reversing && <ReasonDialog title="Reverse these hours?"
      onSubmit={(reason) => reverseTime(reversing.id, reason)}
      onClose={() => setReversing(null)}
      onDone={() => { setReversing(null); refresh(); }} />}
  </section>;
}
