/*
  Enquiry form (F01), used in two places.

  - Publicly at /, the one screen an unauthenticated visitor can use.
  - By staff at /enquiries/new, for a phone call or a walk-in, where
    they also record where the enquiry came from.

  It must never lose a submission, so:

  - the reference number shown comes from the server, after the records
    are committed, never generated here;
  - a failure shows the real reason and keeps everything typed, so it
    can be retried without re-entering anything;
  - only name, phone and address are required, and only those, the
    capacity and what the customer wants are shown at first. Everything
    else sits in closed groups: people rarely have their bill to hand,
    an enquiry is worth more than a complete form, and staff fill in
    the rest from the enquiry later.
*/

import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { describeError, fieldErrorsFrom } from "../../api/client";
import BrandShell from "../../components/BrandShell";
import Button, { ButtonLink } from "../../components/Button";
import { SelectField, TextAreaField, TextField } from "../../components/Field";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { submitEnquiry } from "./api";
import { ABOUT_FIELDS, BILL_FIELDS, groupHasError } from "./detail_groups";
import { AboutFields, BillFields, OptionalSection } from "./enquiry_detail_fields";
import { INDIAN_STATES } from "./states";
import type { EnquiryCreated, EnquiryFormValues } from "./types";
import styles from "./EnquiryForm.module.css";

const EMPTY_FORM: EnquiryFormValues = {
  full_name: "",
  phone: "",
  email: "",
  customer_type: "residential",
  address_line: "",
  city: "",
  state: "",
  pincode: "",
  shadow_free_roof_area_sqm: "",
  source: "phone",
  requested_system_type: "undecided",
  requested_capacity_kw: "",
  electricity_connection_number: "",
  monthly_bill_amount: "",
  monthly_consumption_kwh: "",
  billing_period_start: "",
  billing_period_end: "",
  notes: "",
};

const SOURCE_OPTIONS = [
  { value: "phone", label: "Phone call" },
  { value: "whatsapp", label: "WhatsApp message" },
  { value: "walk_in", label: "Walk-in" },
  { value: "referral", label: "Referral" },
  { value: "other", label: "Other" },
];

const STATE_OPTIONS = INDIAN_STATES.map((state) => ({ value: state, label: state }));

interface EnquiryFormProps {
  staff?: boolean;
}

export default function EnquiryForm({ staff = false }: EnquiryFormProps) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<EnquiryFormValues>(EMPTY_FORM);
  const [bill, setBill] = useState<File | null>(null);
  const [saved, setSaved] = useState<EnquiryCreated | null>(null);

  const mutation = useMutation({
    mutationFn: submitEnquiry,
    onSuccess: (data) => {
      setSaved(data);
      if (staff) queryClient.invalidateQueries({ queryKey: ["enquiries"] });
    },
  });

  function update(name: keyof EnquiryFormValues) {
    return (value: string) =>
      setValues((current) => ({ ...current, [name]: value }));
  }

  function startAnother() {
    setValues(EMPTY_FORM);
    setBill(null);
    setSaved(null);
    mutation.reset();
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    mutation.mutate(buildFormData(values, bill, staff));
  }

  const fieldErrors = fieldErrorsFrom(mutation.error);

  /* A text input bound to one form value, with its server error. */
  function bind(name: keyof EnquiryFormValues) {
    return {
      value: values[name],
      onChange: update(name),
      error: fieldErrors[name]?.[0],
    };
  }

  if (saved) {
    return <Confirmation saved={saved} staff={staff} onAnother={startAnother} />;
  }

  const form = (
    <form onSubmit={handleSubmit} noValidate>
      {mutation.isError && (
        <div className={styles.formError} role="alert">
          {Object.keys(fieldErrors).length > 0
            ? "Please correct the highlighted fields below."
            : describeError(mutation.error)}
        </div>
      )}

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{staff ? "Customer" : "About you"}</h2>
        <div className={styles.grid}>
          <TextField label="Full name" required autoComplete="name" {...bind("full_name")} />
          <TextField
            label="Phone"
            required
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            hint="10 digits. +91 is fine."
            {...bind("phone")}
          />
          {staff && (
            <SelectField
              label="How did they reach us?"
              options={SOURCE_OPTIONS}
              {...bind("source")}
            />
          )}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Where is the roof</h2>
        <div className={styles.grid}>
          <TextField
            label="Address"
            required
            wide
            autoComplete="street-address"
            {...bind("address_line")}
          />
          <TextField label="City" required {...bind("city")} />
          <SelectField
            label="State"
            required
            options={STATE_OPTIONS}
            placeholder="Select a state"
            {...bind("state")}
          />
          <TextField
            label="PIN code"
            required
            inputMode="numeric"
            autoComplete="postal-code"
            {...bind("pincode")}
          />
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>What you need</h2>
        <div className={styles.grid}>
          <TextField
            label="Capacity wanted"
            inputMode="decimal"
            unit="kW"
            hint="Leave blank if you are not sure."
            {...bind("requested_capacity_kw")}
          />
          <TextAreaField
            label="What would you like?"
            wide
            hint="For example: a lower bill, or power during cuts."
            {...bind("notes")}
          />
        </div>
      </section>

      <p className={styles.hint}>
        {staff
          ? "Fill in what the customer knows now. The rest can be added from the enquiry later."
          : "Have your bill to hand? Add it below. If not, we will ask when we call."}
      </p>

      <OptionalSection
        title={staff ? "More about the customer and roof" : "More about you and your roof"}
        summary="Email, property type, system type, roof area"
        hasError={groupHasError(ABOUT_FIELDS, fieldErrors)}
      >
        <AboutFields bind={bind} />
      </OptionalSection>

      <OptionalSection
        title="From the electricity bill"
        summary="Connection number, bill amount, units, the bill itself"
        hasError={groupHasError(BILL_FIELDS, fieldErrors)}
      >
        <BillFields bind={bind} billError={fieldErrors.electricity_bill?.[0]} onBill={setBill} />
      </OptionalSection>

      <Button
        type="submit"
        variant="primary"
        className={styles.submit}
        disabled={mutation.isPending}
      >
        {mutation.isPending ? "Sending…" : staff ? "Save enquiry" : "Send enquiry"}
      </Button>
    </form>
  );

  if (staff) {
    return (
      <div className={styles.staffPage}>
        <PageHeader
          title="New enquiry"
          back={{ to: "/enquiries", label: "Enquiries" }}
        />
        {form}
      </div>
    );
  }

  return (
    <BrandShell panel={<PublicPitch />}>
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Tell us about your roof</h2>
        <p className={styles.intro}>Only the starred fields are needed.</p>
        {form}
      </div>
    </BrandShell>
  );
}


// ============================================================
// Helpers
// ============================================================

/*
  The left side of the public page: who this is, what we install, and
  what happens after sending. Every line comes from what the company
  really offers. No invented customer counts or savings figures.
*/
function PublicPitch() {
  return (
    <>
      <h1 className={styles.headline}>Request a solar quote</h1>
      <p className={styles.lead}>
        Rooftop solar for homes and small businesses, from first call to
        after-sales support.
      </p>

      <ul className={styles.offers}>
        <li>On-grid and off-grid systems, 1 to 5 kW</li>
        <li>Quotations based on a survey of your roof</li>
        <li>20-year panel warranty, 2 years on inverters and batteries</li>
      </ul>

      <h2 className={styles.nextTitle}>What happens next</h2>
      <ol className={styles.steps}>
        <li>We call you to understand your needs</li>
        <li>A technician surveys your roof</li>
        <li>You get a quotation with any subsidy that applies</li>
      </ol>

      <Link className={styles.staffLink} to="/login">
        Staff sign in
      </Link>
    </>
  );
}

/*
  Shown after the records are committed. Staff go straight to the
  enquiry they saved: searching by its reference puts it on the first
  page of the queue, so its panel opens whatever else is waiting.
*/
function Confirmation({
  saved,
  staff,
  onAnother,
}: {
  saved: EnquiryCreated;
  staff: boolean;
  onAnother: () => void;
}) {
  const content = (
    <div className={styles.card}>
      <h1 className={styles.successTitle}>
        {staff ? "Enquiry saved" : "Enquiry received"}
      </h1>
      <p>{staff ? "Its reference is:" : "Keep this reference for any follow-up:"}</p>
      <p className={styles.reference}>
        <Reference>{saved.reference}</Reference>
      </p>
      {staff ? (
        <div className={styles.actions}>
          {saved.id !== undefined && (
            <ButtonLink variant="primary"
              to={`/enquiries?search=${encodeURIComponent(saved.reference)}&selected=${saved.id}`}>
              Open enquiry
            </ButtonLink>
          )}
          <Button onClick={onAnother}>Add another</Button>
          <ButtonLink variant="quiet" to="/enquiries">Back to enquiries</ButtonLink>
        </div>
      ) : (
        <p>Our team will call you shortly to discuss your roof.</p>
      )}
    </div>
  );

  if (staff) return <div className={styles.staffPage}>{content}</div>;
  return <BrandShell panel={<PublicPitch />}>{content}</BrandShell>;
}

/*
  Blank optional fields are left out rather than sent as "", which the
  API would reject as an invalid number. A visitor does not send a
  source: the server records the web form for them.
*/
function buildFormData(values: EnquiryFormValues, bill: File | null, staff: boolean) {
  const data = new FormData();

  for (const [name, value] of Object.entries(values)) {
    const isStaffOnly = name === "source" && !staff;
    if (value !== "" && !isStaffOnly) data.append(name, value);
  }

  if (bill) data.append("electricity_bill", bill);
  return data;
}
