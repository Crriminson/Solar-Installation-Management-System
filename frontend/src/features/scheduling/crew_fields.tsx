/*
  Choosing a crew (F10), wherever a visit is booked.

  The first technician listed leads the job. The staff list returns
  everyone; filtering to technicians here is a convenience. The server
  still refuses anyone who is not one, and is the only judge of who is
  free: a clash comes back as an error naming the job they are on.
*/

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../../api/client";
import Button from "../../components/Button";
import { SelectField } from "../../components/Field";
import { ErrorMessage } from "../../components/StateMessage";
import styles from "./scheduling.module.css";

interface StaffRow {
  id: number;
  name: string;
  roles: string[];
}

export default function CrewFields({ crew, onChange }: {
  crew: string[];
  onChange: (crew: string[]) => void;
}) {
  const staff = useQuery({
    queryKey: ["staff"],
    queryFn: () => apiGet<StaffRow[]>("staff/"),
  });

  if (staff.isError) return <ErrorMessage error={staff.error} onRetry={staff.refetch} />;

  const technicians = (staff.data ?? []).filter(
    (person) => person.roles.includes("technician")
      || person.roles.includes("operations_manager"),
  );

  return <>
    {crew.map((member, index) => <SelectField key={index}
      label={index === 0 ? "Lead technician" : `Technician ${index + 1}`}
      value={member}
      options={[{ value: "", label: staff.isPending ? "Loading…" : "Choose somebody" },
        ...technicians.map((person) => ({ value: String(person.id), label: person.name }))]}
      onChange={(value) => onChange(crew.map(
        (existing, position) => position === index ? value : existing))} />)}

    <div className={styles.actions}>
      <Button type="button" onClick={() => onChange([...crew, ""])}>Add technician</Button>
      {crew.length > 1 && <Button type="button"
        onClick={() => onChange(crew.slice(0, -1))}>Remove last</Button>}
    </div>
  </>;
}
