/* Warranty payloads (F12). Read-only: warranties come from events. */

export type WarrantyState = "in_cover" | "expired" | "replaced";
export type CoverageBasis = "delivery" | "inherited" | "fresh";

export interface Warranty {
  id: number;
  unit: number;
  asset_id: string;
  serial_number: string;
  sku: string;
  product_name: string;
  unit_status: string;
  customer: number;
  customer_name: string;
  site: number;
  site_address: string;
  order: number;
  order_reference: string;
  delivered_at: string;
  policy_name: string;
  policy_version: number;
  duration_months: number;
  coverage_basis: CoverageBasis;
  coverage_start: string;
  coverage_expires_on: string;
  /* Earlier than the expiry once replaced. Null if no day was ever covered. */
  last_covered_on: string | null;
  status: WarrantyState;
  replaces: number | null;
  replaced_by: number | null;
}

export interface HistoryEntry {
  id: number;
  asset_id: string;
  serial_number: string;
  sku: string;
  product_name: string;
  delivered_at: string;
  coverage_basis: CoverageBasis;
  coverage_start: string;
  coverage_expires_on: string;
  last_covered_on: string | null;
  status: WarrantyState;
  replacement_reason: string;
}

export interface WarrantyDetail extends Warranty {
  conditions: string;
  fresh_period_on_replacement: boolean;
  replacement_reason: string;
  history: HistoryEntry[];
}

export interface UncoveredUnit {
  id: number;
  asset_id: string;
  serial_number: string;
  sku: string;
  product_name: string;
}

export interface OrderWarranties {
  warranties: Warranty[];
  uncovered_units: UncoveredUnit[];
}
