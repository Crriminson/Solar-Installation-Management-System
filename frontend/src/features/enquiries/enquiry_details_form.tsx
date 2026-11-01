/*
  Completing an enquiry's details after it arrived (F01).

  The form at intake asks for very little, so what the customer did not
  know is filled in here once sales has spoken to them. Closed until
  asked for, because on most visits to the panel the job is a call or a
  move, not this.

  Every field is sent, so a value cleared here is cleared on the record;
  the server records only what actually changed. The revision is the one
  shown when the form opened, so a change made meanwhile by someone else
  is refused rather than silently overwritten, and the typed values stay.

  Name, phone and address are not editable here: duplicate detection
  compares them, so changing them needs its own rule.
*/

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { describeError, fieldErrorsFrom } from "../../api/client";
import Button from "../../components/Button";
import { TextAreaField, TextField } from "../../components/Field";
import { useToast } from "../../components/ToastContext";
import { updateEnquiryDetails } from "./api";
import { AboutFields, BillFields, type DetailField } from "./enquiry_detail_fields";
import type { EnquiryListItem } from "./types";
import styles from "./enquiry_details_form.module.css";

type EditableField = DetailField | "requested_capacity_kw" | "notes";

export default function CompleteDetails({ enquiry, onDone }: {
  enquiry: EnquiryListItem;
  onDone: () => void;
}) {
  const [editing, setEditing] = useState(false);

  return (
    <section className={styles.section}>
      {editing
        ? <DetailsForm enquiry={enquiry}
            onClose={() => setEditing(false)}
            onSaved={() => { setEditing(false); onDone(); }} />
        : <Button onClick={() => setEditing(true)}>Complete details</Button>}
    </section>
  );
}

function DetailsForm({ enquiry, onClose, onSaved }: {
  enquiry: EnquiryListItem;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [revision] = useState(enquiry.revision);
  const [values, setValues] = useState<Record<EditableField, string>>(() => startingValues(enquiry));
  const [bill, setBill] = useState<File | null>(null);
  const confirm = useToast();

  const mutation = useMutation({
    mutationFn: () => updateEnquiryDetails(enquiry.id, buildFormData(revision, values, bill)),
    onSuccess: () => { confirm(`Details saved on ${enquiry.reference}`); onSaved(); },
  });

  const fieldErrors = fieldErrorsFrom(mutation.error);
  const bind = (name: EditableField) => ({
    value: values[name],
    onChange: (value: string) => setValues((current) => ({ ...current, [name]: value })),
    error: fieldErrors[name]?.[0],
  });

  return (
    <form className={styles.form} noValidate onSubmit={(event) => {
      event.preventDefault();
      mutation.mutate();
    }}>
      <h3 className={styles.title}>Complete details</h3>
      <p className={styles.muted}>Name, phone and address cannot be changed here.</p>

      {mutation.isError && (
        <p className={styles.error} role="alert">
          {Object.keys(fieldErrors).length > 0
            ? "Please correct the highlighted fields."
            : describeError(mutation.error)}
        </p>
      )}

      <TextField label="Capacity wanted" inputMode="decimal" unit="kW"
        {...bind("requested_capacity_kw")} />
      <TextAreaField label="What they would like" {...bind("notes")} />

      <h4 className={styles.groupTitle}>Customer and roof</h4>
      <AboutFields bind={bind} />

      <h4 className={styles.groupTitle}>From the electricity bill</h4>
      {enquiry.has_electricity_bill &&
        <p className={styles.muted}>A bill is already attached. Choosing a file replaces it.</p>}
      <BillFields bind={bind} billError={fieldErrors.electricity_bill?.[0]} onBill={setBill} />

      <div className={styles.actions}>
        <Button type="submit" variant="primary" loading={mutation.isPending}>Save details</Button>
        <Button variant="quiet" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
      </div>
    </form>
  );
}


// ============================================================
// Helpers
// ============================================================

/* What is on the record now, as the text the inputs hold. */
function startingValues(enquiry: EnquiryListItem): Record<EditableField, string> {
  const { site } = enquiry;
  return {
    email: site.customer.email,
    customer_type: site.customer.customer_type,
    requested_system_type: enquiry.requested_system_type,
    shadow_free_roof_area_sqm: site.shadow_free_roof_area_sqm ?? "",
    requested_capacity_kw: enquiry.requested_capacity_kw ?? "",
    electricity_connection_number: enquiry.electricity_connection_number,
    monthly_bill_amount: enquiry.monthly_bill_amount ?? "",
    monthly_consumption_kwh: enquiry.monthly_consumption_kwh ?? "",
    billing_period_start: enquiry.billing_period_start ?? "",
    billing_period_end: enquiry.billing_period_end ?? "",
    notes: enquiry.notes,
  };
}

/* A blank number or date in form data reaches the server as empty, which clears it. */
function buildFormData(revision: number, values: Record<EditableField, string>, bill: File | null) {
  const data = new FormData();
  data.append("revision", String(revision));
  for (const [name, value] of Object.entries(values)) data.append(name, value);
  if (bill) data.append("electricity_bill", bill);
  return data;
}
