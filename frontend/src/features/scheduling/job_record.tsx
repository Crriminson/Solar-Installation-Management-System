/*
  One visit (F10).

  The crew's buttons and the office's buttons are on the same screen,
  shown by role. Rescheduling asks for a reason before it will submit,
  because the previous slot is kept and an unexplained move is the thing
  nobody can answer for later.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { describeError } from "../../api/client";
import Button, { ButtonLink } from "../../components/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import { TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { dateTimeForInput, dateTimeInputToIso, formatDateTime } from "../../lib/format";
import { hasRole, useStaffUser } from "../auth/session";
import TimeSection from "../costing/time_section";
import { openReport } from "../installations/api";
import { cancelJob, fetchJob, rescheduleJob, startJob } from "./api";
import { JOB_KINDS, JOB_STATUSES } from "./status";
import type { Job } from "./types";
import styles from "./scheduling.module.css";

export default function JobRecord() {
  const { jobId = "" } = useParams();
  const result = useQuery({
    queryKey: ["jobs", jobId], queryFn: () => fetchJob(jobId),
  });

  if (result.isPending) return <LoadingMessage label="Loading job…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <JobDetails job={result.data} />;
}

function JobDetails({ job }: { job: Job }) {
  const user = useStaffUser();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["jobs"] });

  const [moving, setMoving] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [startsAt, setStartsAt] = useState(dateTimeForInput(job.starts_at));
  const [endsAt, setEndsAt] = useState(dateTimeForInput(job.ends_at));

  const canSchedule = hasRole(user, "operations_manager");
  const onSite = job.status === "in_progress";

  const starting = useMutation({ mutationFn: () => startJob(job), onSuccess: refresh });
  const moveMutation = useMutation({
    mutationFn: () => rescheduleJob(job, {
      starts_at: dateTimeInputToIso(startsAt),
      ends_at: dateTimeInputToIso(endsAt),
      reason,
    }),
    onSuccess: () => { setMoving(false); refresh(); },
  });
  const cancellation = useMutation({
    mutationFn: () => cancelJob(job, reason),
    onSuccess: () => { setCancelling(false); refresh(); },
  });
  const report = useMutation({
    mutationFn: () => openReport(job.id),
    onSuccess: (created) => navigate(`/installations/${created.id}`),
  });

  return <>
    <PageHeader back={{ to: "/schedule", label: "Schedule" }}
      title={JOB_KINDS[job.kind] ?? job.kind}
      subtitle={`${job.customer_name} · ${job.site_address}`}>
      <StatusBadge status={JOB_STATUSES[job.status]} />
    </PageHeader>

    {job.is_blocked && <p className={styles.blocked}>{job.blocked_reason}</p>}

    <section className={styles.section}>
      <h2>The visit</h2>
      <dl className={styles.facts}>
        <dt>Starts</dt><dd>{formatDateTime(job.starts_at)}</dd>
        <dt>Ends</dt><dd>{formatDateTime(job.ends_at)}</dd>
        <dt>Crew</dt>
        <dd>{job.assignments.map((person) =>
          `${person.technician_name || person.username}${person.is_lead ? " (lead)" : ""}`
        ).join(", ") || "Nobody assigned"}</dd>
        {job.order_reference && <><dt>Order</dt><dd>{job.order_reference}</dd></>}
        {job.notes && <><dt>Notes</dt><dd>{job.notes}</dd></>}
        {job.cancelled_reason &&
          <><dt>Cancelled because</dt><dd>{job.cancelled_reason}</dd></>}
      </dl>
    </section>

    <div className={styles.actions}>
      {job.status === "scheduled" &&
        <Button variant="primary" onClick={() => starting.mutate()}
          disabled={starting.isPending}>Start the visit</Button>}

      {onSite && job.kind === "installation" &&
        <Button variant="primary" onClick={() => report.mutate()}
          disabled={report.isPending}>Record the installation</Button>}

      {canSchedule && job.status !== "completed" && job.status !== "cancelled" && <>
        <Button onClick={() => setMoving(true)}>Reschedule</Button>
        <Button onClick={() => setCancelling(true)}>Cancel visit</Button>
      </>}

      {job.order && <ButtonLink to={`/orders/${job.order}`}>Order</ButtonLink>}
    </div>

    {(starting.isError || report.isError) &&
      <p className={styles.error}>{describeError(starting.error ?? report.error)}</p>}

    <TimeSection jobId={job.id} crew={job.assignments.map((row) => row.technician)} />

    {job.schedule_changes && job.schedule_changes.length > 0 &&
      <section className={styles.section}>
        <h2>Moved before</h2>
        <ul className={styles.history}>
          {job.schedule_changes.map((change) => <li key={change.id}>
            Was {formatDateTime(change.previous_starts_at)} —{" "}
            {change.reason}
            <div className={styles.muted}>
              {change.changed_by_name} · {formatDateTime(change.changed_at)}
            </div>
          </li>)}
        </ul>
      </section>}

    {moving && <ConfirmDialog title="Move this visit"
      confirmLabel="Reschedule" pending={moveMutation.isPending}
      error={moveMutation.isError ? describeError(moveMutation.error) : null}
      onConfirm={() => moveMutation.mutate()} onCancel={() => setMoving(false)}>
      <div className={styles.form}>
        <p>The slot it holds now is kept, along with your reason.</p>
        <TextField label="New start" type="datetime-local" required
          value={startsAt} onChange={setStartsAt} />
        <TextField label="New end" type="datetime-local" required
          value={endsAt} onChange={setEndsAt} />
        <TextAreaField label="Why is it moving?" required value={reason}
          onChange={setReason} />
      </div>
    </ConfirmDialog>}

    {cancelling && <ConfirmDialog title="Cancel this visit"
      confirmLabel="Cancel visit" pending={cancellation.isPending}
      error={cancellation.isError ? describeError(cancellation.error) : null}
      onConfirm={() => cancellation.mutate()} onCancel={() => setCancelling(false)}>
      <TextAreaField label="Why is it cancelled?" required value={reason}
        onChange={setReason} />
    </ConfirmDialog>}
  </>;
}
