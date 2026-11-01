/*
  The optional details of an enquiry (F01), as two collapsible groups.

  The same groups appear on the enquiry form and on the staff screen
  that fills them in later, so the two always ask for the same things.
  Closed by default, because most people do not have this to hand and a
  long form loses enquiries. A group opens by itself when the server
  rejects one of its fields, so an error is never hidden.
*/

import { useState, type ReactNode } from "react";

import { FileField, SelectField, TextField } from "../../components/Field";
import { CaretDownIcon, ICON_SIZE } from "../../design/icons";
import styles from "./enquiry_detail_fields.module.css";

export type DetailField =
  | "email"
  | "customer_type"
  | "requested_system_type"
  | "shadow_free_roof_area_sqm"
  | "electricity_connection_number"
  | "monthly_bill_amount"
  | "monthly_consumption_kwh"
  | "billing_period_start"
  | "billing_period_end";

export interface BoundField {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}

type Bind = (name: DetailField) => BoundField;

const CUSTOMER_TYPE_OPTIONS = [
  { value: "residential", label: "Home" },
  { value: "commercial", label: "Business" },
];

const SYSTEM_TYPE_OPTIONS = [
  { value: "undecided", label: "Not sure yet" },
  { value: "on_grid", label: "On-grid" },
  { value: "off_grid", label: "Off-grid, with battery" },
];

const BILL_FILE_TYPES = ".pdf,.jpg,.jpeg,.png";


// ============================================================
// The groups
// ============================================================

export function OptionalSection({ title, summary, hasError, children }: {
  title: string;
  summary: string;
  hasError: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <details
      className={styles.group}
      open={open || hasError}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className={styles.summary}>
        <span>
          <span className={styles.title}>{title}</span>
          <span className={styles.optional}> · optional</span>
          <span className={styles.description}>{summary}</span>
        </span>
        <CaretDownIcon className={styles.caret} size={ICON_SIZE.inline} aria-hidden />
      </summary>
      <div className={styles.body}>{children}</div>
    </details>
  );
}

export function AboutFields({ bind }: { bind: Bind }) {
  return (
    <div className={styles.grid}>
      <TextField label="Email" type="email" inputMode="email" autoComplete="email"
        {...bind("email")} />
      <SelectField label="Property type" options={CUSTOMER_TYPE_OPTIONS}
        {...bind("customer_type")} />
      <SelectField label="System type" options={SYSTEM_TYPE_OPTIONS}
        {...bind("requested_system_type")} />
      <TextField label="Shadow-free roof area" inputMode="decimal" unit="m²"
        hint="Open to the sun for most of the day." {...bind("shadow_free_roof_area_sqm")} />
    </div>
  );
}

export function BillFields({ bind, billError, onBill }: {
  bind: Bind;
  billError?: string;
  onBill: (file: File | null) => void;
}) {
  return (
    <div className={styles.grid}>
      <TextField label="Connection number" hint="Printed on the electricity bill."
        {...bind("electricity_connection_number")} />
      {/* Bill amount and units are asked separately on purpose:
          a slabbed tariff means neither gives you the other. */}
      <TextField label="Monthly bill" inputMode="decimal" unit="₹"
        hint="Needs the billing period below." {...bind("monthly_bill_amount")} />
      <TextField label="Monthly units" inputMode="decimal" unit="kWh"
        hint="On the bill, separate from the amount." {...bind("monthly_consumption_kwh")} />
      <TextField label="Billing period from" type="date" {...bind("billing_period_start")} />
      <TextField label="Billing period to" type="date" {...bind("billing_period_end")} />
      <FileField label="Electricity bill" wide accept={BILL_FILE_TYPES}
        hint="PDF, JPEG or PNG, up to 10 MB." error={billError} onChange={onBill} />
    </div>
  );
}
