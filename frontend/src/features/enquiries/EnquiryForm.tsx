/*
  Public enquiry form (F01).

  The one screen an unauthenticated visitor can use. It must never lose
  a submission, so:

  - the reference number shown comes from the server, after the records
    are committed, never generated here;
  - a failure shows the real reason and keeps everything the visitor
    typed, so they can retry without re-entering anything;
  - only name, phone and address are required. Electricity details are
    optional because a visitor rarely has their bill to hand, and an
    enquiry is worth more than a complete form.
*/

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { submitEnquiry } from "./api";
import { INDIAN_STATES } from "./states";
import type { EnquiryFormValues } from "./types";
import { ApiError } from "../../api/client";
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
  requested_system_type: "undecided",
  requested_capacity_kw: "",
  monthly_bill_amount: "",
  monthly_consumption_kwh: "",
  notes: "",
};

/* Field errors arrive from the API as { field: ["message"] }. */
type FieldErrors = Record<string, string[]>;

export default function EnquiryForm() {
  const [values, setValues] = useState<EnquiryFormValues>(EMPTY_FORM);
  const [reference, setReference] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: submitEnquiry,
    onSuccess: (data) => setReference(data.reference),
  });

  function updateField(name: keyof EnquiryFormValues, value: string) {
    setValues((current) => ({ ...current, [name]: value }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    // Blank optional fields are dropped rather than sent as "", which
    // the API would reject as an invalid number.
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== ""),
    );
    mutation.mutate(payload);
  }

  const fieldErrors: FieldErrors =
    mutation.error instanceof ApiError &&
    mutation.error.details &&
    typeof mutation.error.details === "object"
      ? (mutation.error.details as FieldErrors)
      : {};

  function errorFor(field: keyof EnquiryFormValues) {
    return fieldErrors[field]?.[0];
  }

  // --- after a successful submission --------------------------------

  if (reference) {
    return (
      <main className={styles.page}>
        <div className={styles.success}>
          <h1>Enquiry received</h1>
          <p>Keep this reference for any follow-up:</p>
          <p className={styles.reference}>{reference}</p>
          <p>Our team will call you shortly to discuss your roof.</p>
        </div>
      </main>
    );
  }

  // --- the form -----------------------------------------------------

  return (
    <main className={styles.page}>
      <h1>Request a solar quote</h1>
      <p className={styles.intro}>
        Tell us about your roof and we will get back to you. Only the
        starred fields are needed.
      </p>

      {mutation.isError && (
        <div className={styles.formError} role="alert">
          {Object.keys(fieldErrors).length > 0
            ? "Please correct the highlighted fields below."
            : "We could not submit your enquiry. Please try again."}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>About you</h2>
          <div className={styles.grid}>
            <Field
              label="Full name"
              name="full_name"
              required
              value={values.full_name}
              error={errorFor("full_name")}
              onChange={updateField}
            />
            <Field
              label="Phone"
              name="phone"
              required
              value={values.phone}
              error={errorFor("phone")}
              hint="10 digits. +91 is fine."
              onChange={updateField}
            />
            <Field
              label="Email"
              name="email"
              type="email"
              value={values.email}
              error={errorFor("email")}
              onChange={updateField}
            />
            <div className={styles.field}>
              <label className={styles.label} htmlFor="customer_type">
                Property type
              </label>
              <select
                id="customer_type"
                className={styles.select}
                value={values.customer_type}
                onChange={(e) => updateField("customer_type", e.target.value)}
              >
                <option value="residential">Home</option>
                <option value="commercial">Business</option>
              </select>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Where is the roof</h2>
          <div className={styles.grid}>
            <div className={`${styles.field} ${styles.fieldWide}`}>
              <label className={`${styles.label} ${styles.required}`} htmlFor="address_line">
                Address
              </label>
              <input
                id="address_line"
                className={styles.input}
                value={values.address_line}
                onChange={(e) => updateField("address_line", e.target.value)}
              />
              {errorFor("address_line") && (
                <span className={styles.fieldError}>{errorFor("address_line")}</span>
              )}
            </div>
            <Field
              label="City"
              name="city"
              required
              value={values.city}
              error={errorFor("city")}
              onChange={updateField}
            />
            <div className={styles.field}>
              <label className={`${styles.label} ${styles.required}`} htmlFor="state">
                State
              </label>
              <select
                id="state"
                className={styles.select}
                value={values.state}
                onChange={(e) => updateField("state", e.target.value)}
              >
                <option value="">Select a state</option>
                {INDIAN_STATES.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
              {errorFor("state") && (
                <span className={styles.fieldError}>{errorFor("state")}</span>
              )}
            </div>
            <Field
              label="PIN code"
              name="pincode"
              required
              value={values.pincode}
              error={errorFor("pincode")}
              onChange={updateField}
            />
          </div>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Your electricity use</h2>
          <p className={styles.hint}>
            All optional. Skip anything you do not know.
          </p>
          <div className={styles.grid}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="requested_system_type">
                System type
              </label>
              <select
                id="requested_system_type"
                className={styles.select}
                value={values.requested_system_type}
                onChange={(e) =>
                  updateField("requested_system_type", e.target.value)
                }
              >
                <option value="undecided">Not sure yet</option>
                <option value="on_grid">On-grid</option>
                <option value="off_grid">Off-grid, with battery</option>
              </select>
            </div>
            <Field
              label="Capacity wanted (kW)"
              name="requested_capacity_kw"
              type="number"
              value={values.requested_capacity_kw}
              error={errorFor("requested_capacity_kw")}
              onChange={updateField}
            />
            {/* Bill amount and units are asked separately on purpose:
                a slabbed tariff means neither gives you the other. */}
            <Field
              label="Monthly bill (INR)"
              name="monthly_bill_amount"
              type="number"
              value={values.monthly_bill_amount}
              error={errorFor("monthly_bill_amount")}
              onChange={updateField}
            />
            <Field
              label="Monthly units (kWh)"
              name="monthly_consumption_kwh"
              type="number"
              value={values.monthly_consumption_kwh}
              error={errorFor("monthly_consumption_kwh")}
              hint="On your bill, separate from the amount."
              onChange={updateField}
            />
            <div className={`${styles.field} ${styles.fieldWide}`}>
              <label className={styles.label} htmlFor="notes">
                Anything else
              </label>
              <textarea
                id="notes"
                className={styles.textarea}
                value={values.notes}
                onChange={(e) => updateField("notes", e.target.value)}
              />
            </div>
          </div>
        </section>

        <button
          type="submit"
          className={styles.submit}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? "Sending…" : "Send enquiry"}
        </button>
      </form>
    </main>
  );
}


// ============================================================
// Helpers
// ============================================================

interface FieldProps {
  label: string;
  name: keyof EnquiryFormValues;
  value: string;
  onChange: (name: keyof EnquiryFormValues, value: string) => void;
  type?: string;
  required?: boolean;
  hint?: string;
  error?: string;
}

/* A labelled text input with its hint and error message. */
function Field({
  label,
  name,
  value,
  onChange,
  type = "text",
  required = false,
  hint,
  error,
}: FieldProps) {
  return (
    <div className={styles.field}>
      <label
        className={`${styles.label} ${required ? styles.required : ""}`}
        htmlFor={name}
      >
        {label}
      </label>
      <input
        id={name}
        className={styles.input}
        type={type}
        value={value}
        onChange={(event) => onChange(name, event.target.value)}
      />
      {hint && !error && <span className={styles.hint}>{hint}</span>}
      {error && <span className={styles.fieldError}>{error}</span>}
    </div>
  );
}
