/*
  Which optional enquiry details sit in which collapsible group (F01).

  Kept out of enquiry_detail_fields.tsx so that file exports components
  only, which keeps fast refresh working during development.
*/

export const ABOUT_FIELDS: readonly string[] = [
  "email", "customer_type", "requested_system_type", "shadow_free_roof_area_sqm",
];

export const BILL_FIELDS: readonly string[] = [
  "electricity_connection_number", "monthly_bill_amount", "monthly_consumption_kwh",
  "billing_period_start", "billing_period_end", "electricity_bill",
];

/* True when the server named any field in this group, so it can open. */
export function groupHasError(fields: readonly string[], errors: Record<string, unknown>) {
  return fields.some((field) => field in errors);
}
