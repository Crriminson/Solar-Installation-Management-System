/*
  The on-site form (F11).

  Filled in on a phone on a roof, so it saves what is there rather than
  demanding everything at once, and it shows what is still outstanding
  the whole time. The crew should never press Submit and be told, for
  the first time, that six things are missing.

  Serials are scanned the same way as in packing: the input stays
  focused and submits on Enter.
*/

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { describeError } from "../../api/client";
import Button from "../../components/Button";
import { SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import StatusBadge from "../../components/StatusBadge";
import { dateTimeForInput, dateTimeInputToIso, nowForDateTimeInput } from "../../lib/format";
import { addInstalledUnit, addPhoto, fetchReport, submitReport,
         updateReport } from "./api";
import { REPORT_STATUSES } from "./status";
import type { ChecklistEntry, InstallationReport } from "./types";
import styles from "./installations.module.css";

export default function InstallationForm() {
  const { reportId = "" } = useParams();
  const result = useQuery({
    queryKey: ["installations", reportId],
    queryFn: () => fetchReport(reportId),
  });

  if (result.isPending) return <LoadingMessage label="Loading the form…" />;
  if (result.isError) return <ErrorMessage error={result.error} onRetry={result.refetch} />;
  return <Form report={result.data} />;
}

function Form({ report }: { report: InstallationReport }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["installations"] });

  const [startedAt, setStartedAt] = useState(
    report.started_at ? dateTimeForInput(report.started_at) : nowForDateTimeInput());
  const [finishedAt, setFinishedAt] = useState(
    report.finished_at ? dateTimeForInput(report.finished_at) : nowForDateTimeInput());
  const [systemType, setSystemType] = useState(report.system_type || "on_grid");
  const [capacity, setCapacity] = useState(report.installed_capacity_kw ?? "");
  const [testKw, setTestKw] = useState(report.generation_test_kw ?? "");
  const [testPassed, setTestPassed] = useState(
    report.generation_test_passed === null ? "" : String(report.generation_test_passed));
  const [testNotes, setTestNotes] = useState(report.generation_test_notes);
  const [notes, setNotes] = useState(report.notes);
  const [checks, setChecks] = useState<Record<string, boolean>>(
    Object.fromEntries(report.checklist.map((entry) => [entry.item, entry.passed])));

  const saving = useMutation({
    mutationFn: () => updateReport(report, {
      started_at: dateTimeInputToIso(startedAt),
      finished_at: dateTimeInputToIso(finishedAt),
      system_type: systemType,
      installed_capacity_kw: capacity || undefined,
      generation_test_kw: testKw || null,
      generation_test_passed: testPassed === "" ? undefined : testPassed === "true",
      generation_test_notes: testNotes,
      notes,
      checklist: report.mandatory_checks
        .filter((item) => item in checks)
        .map((item): ChecklistEntry => ({ item, passed: checks[item] })),
    }),
    onSuccess: refresh,
  });

  const submitting = useMutation({
    mutationFn: () => submitReport(report),
    onSuccess: () => { refresh(); navigate(`/installations/${report.id}/accept`); },
  });

  const open = report.status === "draft" || report.status === "refused";

  return <>
    <PageHeader back={{ to: `/schedule/${report.job}`, label: "Back to the job" }}
      title="Installation record" subtitle={report.customer_name}
      status={<StatusBadge status={REPORT_STATUSES[report.status]} />} />

    {report.status === "refused" && report.acceptance &&
      <p className={styles.blocked}>
        The customer refused: {report.acceptance.refusal_reason}
      </p>}

    {report.missing_evidence.length > 0 && <div className={styles.todo}>
      <strong>Still needed before the customer can sign</strong>
      <ul>{report.missing_evidence.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>}

    {open && <>
      <section className={styles.section}>
        <h2>The work</h2>
        <div className={styles.form}>
          <TextField label="Actually started" type="datetime-local" value={startedAt}
            onChange={setStartedAt} />
          <TextField label="Actually finished" type="datetime-local" value={finishedAt}
            onChange={setFinishedAt} />
          <SelectField label="Confirmed system type" value={systemType}
            options={[{ value: "on_grid", label: "On-grid" },
                      { value: "off_grid", label: "Off-grid" }]}
            onChange={setSystemType} />
          <TextField label="Installed capacity (kW)" inputMode="decimal"
            value={String(capacity)} onChange={setCapacity}
            hint="What is actually on the roof, not what was quoted." />
        </div>
      </section>

      <section className={styles.section}>
        <h2>Checks</h2>
        {report.mandatory_checks.map((item) => <label key={item} className={styles.check}>
          <input type="checkbox" checked={checks[item] ?? false}
            onChange={(event) => setChecks({ ...checks, [item]: event.target.checked })} />
          {item.replaceAll("_", " ")}
        </label>)}
      </section>

      <section className={styles.section}>
        <h2>Generation test</h2>
        <div className={styles.form}>
          <TextField label="Output measured (kW)" inputMode="decimal" value={String(testKw)}
            onChange={setTestKw} />
          <SelectField label="Did it pass?" value={testPassed}
            options={[{ value: "", label: "Not tested yet" },
                      { value: "true", label: "Passed" },
                      { value: "false", label: "Failed" }]}
            onChange={setTestPassed} />
          <TextAreaField label="Test notes" value={testNotes} onChange={setTestNotes} />
        </div>
      </section>

      <section className={styles.section}>
        <h2>Notes</h2>
        <TextAreaField label="Anything the office should know" value={notes}
          onChange={setNotes} />
      </section>

      <div className={styles.actions}>
        <Button onClick={() => saving.mutate()} disabled={saving.isPending}>
          {saving.isPending ? "Saving…" : "Save"}
        </Button>
        {saving.isError && <span className={styles.error}>{describeError(saving.error)}</span>}
      </div>

      <SerialSection report={report} onChanged={refresh} />
      <PhotoSection report={report} onChanged={refresh} />

      <div className={styles.actions}>
        <Button variant="primary"
          disabled={report.missing_evidence.length > 0 || submitting.isPending}
          onClick={() => submitting.mutate()}>
          Finish and show the customer
        </Button>
        {submitting.isError &&
          <span className={styles.error}>{describeError(submitting.error)}</span>}
      </div>
    </>}

    {!open && <RecordedFacts report={report} />}
  </>;
}

// ============================================================
// Serials
// ============================================================

function SerialSection({ report, onChanged }: {
  report: InstallationReport; onChanged: () => void;
}) {
  const [code, setCode] = useState("");
  const [position, setPosition] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () => addInstalledUnit(report.id, code, position),
    onSuccess: () => {
      setCode("");
      setPosition("");
      onChanged();
      inputRef.current?.focus();
    },
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (code.trim()) mutation.mutate();
  }

  return <section className={styles.section}>
    <h2>What went on the roof</h2>
    <form className={styles.form} onSubmit={submit}>
      <label className={styles.scanLabel} htmlFor="serial">Scan a serial or asset id</label>
      <input id="serial" ref={inputRef} className={styles.scanInput} value={code}
        onChange={(event) => setCode(event.target.value)} autoComplete="off" />
      <TextField label="Where it sits" value={position} onChange={setPosition}
        hint="Optional. For example: south array, row 2." />
      <Button type="submit" disabled={!code.trim() || mutation.isPending}>Add</Button>
      {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}
    </form>

    <ul className={styles.serialList}>
      {report.installed_units.map((entry) => <li key={entry.id}>
        {entry.asset_id}
        {entry.serial_number && ` · ${entry.serial_number}`}
        {" — "}{entry.name}
        {entry.position_note && <span className={styles.muted}> ({entry.position_note})</span>}
      </li>)}
    </ul>
  </section>;
}

// ============================================================
// Photos
// ============================================================

function PhotoSection({ report, onChanged }: {
  report: InstallationReport; onChanged: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");

  const mutation = useMutation({
    mutationFn: () => addPhoto(report.id, file!, caption),
    onSuccess: () => { setFile(null); setCaption(""); onChanged(); },
  });

  return <section className={styles.section}>
    <h2>Photographs</h2>
    <div className={styles.form}>
      <input type="file" accept="image/jpeg,image/png" capture="environment"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      <TextField label="Caption" required value={caption} onChange={setCaption}
        hint="Say what the photo shows. An uncaptioned photo is of nothing." />
      <Button disabled={!file || !caption.trim() || mutation.isPending}
        onClick={() => mutation.mutate()}>Attach</Button>
      {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}
    </div>

    <ul className={styles.photoList}>
      {report.photos.map((photo) => <li key={photo.id}>
        <img src={photo.image} alt={photo.caption} />
        <span>{photo.caption}</span>
      </li>)}
    </ul>
  </section>;
}

function RecordedFacts({ report }: { report: InstallationReport }) {
  return <section className={styles.section}>
    <h2>Recorded</h2>
    <dl className={styles.facts}>
      <dt>Capacity installed</dt><dd>{report.installed_capacity_kw} kW</dd>
      <dt>Generation test</dt>
      <dd>{report.generation_test_passed ? "Passed" : "Failed"}
        {report.generation_test_kw && ` at ${report.generation_test_kw} kW`}</dd>
      <dt>Equipment</dt>
      <dd>{report.installed_units.map((entry) => entry.asset_id).join(", ")}</dd>
      {report.acceptance && <>
        <dt>Customer</dt>
        <dd>{report.acceptance.customer_name} — {report.acceptance.decision}</dd>
      </>}
    </dl>
  </section>;
}
