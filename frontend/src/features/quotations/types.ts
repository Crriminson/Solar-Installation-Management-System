/* Generated quotation documents contain selling values and frozen source details. */

export interface QuoteLine {
  id: number;
  sku: string;
  description: string;
  unit: string;
  quantity: string;
  unit_price_excl_tax: string;
  gst_rate_percent: string;
  net_excl_tax: string;
  tax_amount: string;
  gross_incl_tax: string;
}

export interface SubsidyEstimate {
  rule_id: number;
  scheme: string;
  version: number;
  rule_type: "capital" | "generation";
  amount: string;
  unit: string;
  source_url: string;
  last_checked: string;
  provenance: string;
  assumptions: Record<string, string | boolean>;
}

export interface Quotation {
  id: number;
  reference: string;
  enquiry: number;
  revision_number: number;
  revision: number;
  status: string;
  display_status: string;
  snapshot: {
    customer: { name: string; phone: string; email: string; type: string };
    site: { address: string; city: string; state: string; pincode: string };
    survey: { number: number; recommended_capacity_kw: string; recommended_system_type: string };
    package: { name: string; version: number };
    rounding: string;
  };
  lines: QuoteLine[];
  subsidy: SubsidyEstimate[];
  terms: {
    plan: string;
    advance_percent: string;
    advance_amount_incl_tax: string;
    balance_amount_incl_tax: string;
    notes: string;
  };
  subtotal_excl_tax: string;
  tax_amount: string;
  gross_payable_incl_tax: string;
  validity_days: number;
  valid_until: string | null;
  created_at: string;
  issued_at: string | null;
  content_hash: string;
  requires_survey_review: boolean;
  actions: string[];
}
