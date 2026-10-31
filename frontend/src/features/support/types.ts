/* Support payloads (F13). */

import type { Warranty } from "../warranties/types";

export type TicketState = "new" | "diagnosed" | "in_progress" | "awaiting_confirmation" | "closed";
export type Assessment = "covered" | "not_covered" | "review";

export interface TicketRow {
  id: number;
  reference: string;
  status: TicketState;
  priority: "low" | "normal" | "high";
  customer: number;
  customer_name: string;
  fault_description: string;
  owner: number | null;
  owner_name: string;
  is_blocked: boolean;
  complaint_at: string;
  covered: boolean;
}

export interface TicketAsset {
  id: number;
  unit: number;
  asset_id: string;
  serial_number: string;
  sku: string;
  product_name: string;
  warranty: number | null;
  policy_name: string;
  last_covered_on: string | null;
  assessment: Assessment;
  review_reason: string;
  reviewed_at: string | null;
  replaced: boolean;
}

export interface EstimateLine {
  id: number;
  sku: string;
  description: string;
  unit: string;
  quantity: string;
  unit_price_excl_tax: string;
  gst_rate_percent: string;
  net_excl_tax: string;
  tax_amount: string;
}

export interface RepairEstimate {
  id: number;
  number: number;
  status: "pending" | "approved" | "declined" | "superseded";
  net_excl_tax: string;
  tax_amount: string;
  gross_incl_tax: string;
  decided_by_name: string;
  decided_at: string | null;
  created_at: string;
  lines: EstimateLine[];
}

export interface WorkLine {
  id: number;
  asset: number;
  sku: string;
  description: string;
  unit: string;
  quantity: string;
  charge_excl_tax: string;
  charge_tax: string;
  /* Only sent to those who may see cost. */
  unit_cost?: string;
  invoice: number | null;
  invoice_reference: string;
  voided_reason: string;
  recorded_at: string;
}

export interface ReplacementRecord {
  id: number;
  asset: number;
  old_unit: number;
  old_asset_id: string;
  new_unit: number;
  new_asset_id: string;
  disposition: "returned" | "quarantined";
  new_warranty: number | null;
  reason: string;
  replaced_at: string;
}

export interface Visit {
  id: number;
  status: string;
  starts_at: string;
  ends_at: string;
  technicians: string[];
}

export interface Ticket extends TicketRow {
  customer_phone?: string;
  site: number;
  site_address: string;
  order: number;
  order_reference: string;
  fault_code: string;
  claimed_complaint_at: string | null;
  findings: string;
  recommendation: string;
  diagnosed_at: string | null;
  blocked_reason: string;
  blocked_owner: number | null;
  confirmed_by_name: string;
  confirmed_at: string | null;
  revision: number;
  assets: TicketAsset[];
  estimates: RepairEstimate[];
  work_lines: WorkLine[];
  replacements: ReplacementRecord[];
  photos: { id: number; caption: string; uploaded_at: string }[];
  visits: Visit[];
  allowed_actions: string[];
}

export interface LookupResult {
  customers: { id: number; name: string; phone: string }[];
  assets: Warranty[];
}

export interface CustomerEquipment {
  id: number;
  name: string;
  phone: string;
  units: {
    id: number;
    asset_id: string;
    serial_number: string;
    sku: string;
    product_name: string;
    order_reference: string;
    warranty: Warranty | null;
  }[];
}
