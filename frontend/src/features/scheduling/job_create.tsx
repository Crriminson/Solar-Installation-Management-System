/*
  Book a visit (F10).

  The clash check is the server's. This screen does not try to predict
  it: it submits and shows what came back, naming the job the technician
  is already on. Guessing here would mean holding a copy of everyone's
  diary in the browser and getting it wrong.
*/

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiGet, describeError } from "../../api/client";
import Button from "../../components/Button";
import { SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { dateTimeInputToIso, nowForDateTimeInput } from "../../lib/format";
import { createJob } from "./api";
import { JOB_KINDS } from "./status";
import styles from "./scheduling.module.css";

interface StaffRow {
  id: number;
  name: string;
  roles: string[];
}

interface SiteRow {
  id: number;
  address_line: string;
  city: string;
  customer_name: string;
}

export default function JobCreate() {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [kind, setKind] = useState(params.get("kind") ?? "installation");
  const [site, setSite] = useState(params.get("site") ?? "");
  const [order] = useState(params.get("order") ?? "");
  const [startsAt, setStartsAt] = useState(nowForDateTimeInput());
  const [endsAt, setEndsAt] = useState(nowForDateTimeInput());
  const [notes, setNotes] = useState("");
  const [crew, setCrew] = useState<string[]>([""]);

  /* The staff picker returns everyone; filtering to technicians here is
     a convenience. The server still refuses anyone who is not one. */
  const staff = useQuery({
    queryKey: ["staff"],
    queryFn: () => apiGet<StaffRow[]>("staff/"),
  });
  const sites = useQuery({
    queryKey: ["sites"],
    queryFn: () => apiGet<SiteRow[]>("sites/"),
  });

  const mutation = useMutation({
    mutationFn: () => createJob({
      kind,
      site: Number(site),
      order: order ? Number(order) : null,
      starts_at: dateTimeInputToIso(startsAt),
      ends_at: dateTimeInputToIso(endsAt),
      notes,
      technicians: crew.filter(Boolean).map(Number),
    }),
    onSuccess: (job) => navigate(`/schedule/${job.id}`),
  });

  if (staff.isPending || sites.isPending) return <LoadingMessage label="Loading…" />;
  if (staff.isError) return <ErrorMessage error={staff.error} onRetry={staff.refetch} />;
  if (sites.isError) return <ErrorMessage error={sites.error} onRetry={sites.refetch} />;

  const technicians = staff.data.filter(
    (person) => person.roles.includes("technician")
      || person.roles.includes("operations_manager"),
  );
  const ready = site !== "" && crew.some(Boolean);

  return <>
    <PageHeader back={{ to: "/schedule", label: "Schedule" }} title="Book a visit"
      subtitle="The first technician listed leads the job." />

    <div className={styles.form}>
      <SelectField label="What kind of visit" value={kind} onChange={setKind}
        options={Object.entries(JOB_KINDS).map(([value, label]) => ({ value, label }))} />

      <SelectField label="Site" required value={site} onChange={setSite}
        options={[{ value: "", label: "Choose a site" },
          ...sites.data.map((row) => ({
            value: String(row.id),
            label: `${row.customer_name} — ${row.address_line}, ${row.city}`,
          }))]} />

      <TextField label="Starts" type="datetime-local" required value={startsAt}
        onChange={setStartsAt} />
      <TextField label="Ends" type="datetime-local" required value={endsAt}
        onChange={setEndsAt} />

      <h2>Crew</h2>
      {crew.map((member, index) => <SelectField key={index}
        label={index === 0 ? "Lead technician" : `Technician ${index + 1}`}
        value={member}
        options={[{ value: "", label: "Choose somebody" },
          ...technicians.map((person) => ({
            value: String(person.id), label: person.name,
          }))]}
        onChange={(value) => setCrew(crew.map(
          (existing, position) => position === index ? value : existing))} />)}

      <div className={styles.actions}>
        <Button type="button" onClick={() => setCrew([...crew, ""])}>Add technician</Button>
        {crew.length > 1 && <Button type="button"
          onClick={() => setCrew(crew.slice(0, -1))}>Remove last</Button>}
      </div>

      <TextAreaField label="Notes for the crew" value={notes} onChange={setNotes} />

      {mutation.isError && <p className={styles.error}>{describeError(mutation.error)}</p>}
      <Button variant="primary" disabled={!ready || mutation.isPending}
        onClick={() => mutation.mutate()}>
        {mutation.isPending ? "Booking…" : "Book the visit"}
      </Button>
    </div>
  </>;
}
