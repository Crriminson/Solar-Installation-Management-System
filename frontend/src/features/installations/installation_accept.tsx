/*
  Handover (F11).

  The customer reads what was installed and either signs or says why
  not. Refusal is given equal weight on the screen deliberately: if
  declining is hidden behind a small grey link, crews will press Accept
  for them, and the signature stops meaning anything.

  The revision on screen goes up with the decision, so a report that
  changed while the customer was reading is refused by the server
  rather than silently signed.
*/

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import { TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import SignaturePad from "../../components/signature_pad";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { formatDateTime } from "../../lib/format";
import { decide, fetchReport } from "./api";
import type { InstallationReport } from "./types";
import styles from "./installations.module.css";

export default function InstallationAccept() {
  const { reportId = "" } = useParams();
  const result = useQuery({
    queryKey: ["installations", reportId],
    queryFn: () => fetchReport(reportId),
  });

  if (result.isPending) return <LoadingMessage label="Loading…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <Handover report={result.data} />;
}

function Handover({ report }: { report: InstallationReport }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [customerName, setCustomerName] = useState("");
  const [signature, setSignature] = useState<Blob | null>(null);
  const [refusing, setRefusing] = useState(false);
  const [refusalReason, setRefusalReason] = useState("");

  const mutation = useMutation({
    mutationFn: (choice: "accepted" | "refused") => decide(report, {
      decision: choice,
      customerName,
      signature: choice === "accepted" ? signature : null,
      refusalReason: choice === "refused" ? refusalReason : undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["installations"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      navigate(`/installations/${report.id}`);
    },
  });

  if (report.status !== "submitted") {
    return <>
      <PageHeader title="Handover"
        subtitle="This installation has already been decided." />
      <Button onClick={() => navigate(`/installations/${report.id}`)}>
        Back to the record
      </Button>
    </>;
  }

  const named = customerName.trim().length > 0;

  return <>
    <PageHeader title="Your installation" subtitle={report.customer_name} />

    <section className={styles.section}>
      <h2>What was installed</h2>
      <dl className={styles.facts}>
        <dt>System</dt>
        <dd>{report.system_type.replace("_", "-")} · {report.installed_capacity_kw} kW</dd>
        <dt>Work done</dt>
        <dd>{report.started_at && formatDateTime(report.started_at)}
          {report.finished_at && ` to ${formatDateTime(report.finished_at)}`}</dd>
        <dt>Generation test</dt>
        <dd>{report.generation_test_passed ? "Passed" : "Failed"}
          {report.generation_test_kw && ` — ${report.generation_test_kw} kW measured`}</dd>
      </dl>

      <h3>Equipment, by serial number</h3>
      <ul className={styles.serialList}>
        {report.installed_units.map((entry) => <li key={entry.id}>
          {entry.name} — {entry.serial_number || entry.asset_id}
        </li>)}
      </ul>

      {report.photos.length > 0 && <>
        <h3>Photographs</h3>
        <ul className={styles.photoList}>
          {report.photos.map((photo) => <li key={photo.id}>
            <img src={photo.image} alt={photo.caption} />
            <span>{photo.caption}</span>
          </li>)}
        </ul>
      </>}
    </section>

    <section className={styles.section}>
      <h2>{refusing ? "What is wrong?" : "Accept this installation"}</h2>
      <div className={styles.form}>
        <TextField label="Your full name" required value={customerName}
          onChange={setCustomerName} />

        {refusing
          ? <TextAreaField label="What needs putting right?" required
              value={refusalReason} onChange={setRefusalReason} />
          : <SignaturePad label="Your signature" onChange={setSignature} />}

        {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}

        {refusing
          ? <div className={styles.actions}>
              <Button variant="primary"
                disabled={!named || !refusalReason.trim() || mutation.isPending}
                onClick={() => mutation.mutate("refused")}>
                Record what is wrong
              </Button>
              <Button onClick={() => setRefusing(false)}>Back</Button>
            </div>
          : <div className={styles.actions}>
              <Button variant="primary" disabled={!named || !signature || mutation.isPending}
                onClick={() => mutation.mutate("accepted")}>
                Accept the installation
              </Button>
              <Button onClick={() => setRefusing(true)}>
                I am not happy with this
              </Button>
            </div>}
      </div>
    </section>
  </>;
}
