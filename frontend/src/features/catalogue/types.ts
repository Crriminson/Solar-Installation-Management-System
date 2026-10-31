/* Shapes the catalogue API sends and receives (F04). */

export interface ProductPrice {
  id: number;
  selling_price_excl_tax: string;
  purchase_cost_excl_tax?: string | null;      // absent unless permitted
  effective_from: string;
  created_at: string;
}

export interface Product {
  revision: number;
  id: number;
  sku: string;
  name: string;
  description: string;
  category: string;
  tracking_method: string;
  unit: string;
  stocking_quantity: string;
  gst_rate_percent: string;
  warranty_policy: number | null;
  warranty_policy_name: string;
  rated_power_w: string | null;
  storage_kwh: string | null;
  nominal_voltage_v: string | null;
  is_repair_part: boolean;
  is_active: boolean;
  current_price: ProductPrice | null;
  prices: ProductPrice[];
}

export interface WarrantyPolicy {
  id: number;
  name: string;
  duration_months: number;
}

export type QuantityBasis = "fixed" | "cable_route" | "battery_load";

export interface PackageLine {
  id: number;
  product: number;
  sku: string;
  product_name: string;
  unit: string;
  basis: QuantityBasis;
  quantity: string | null;
  notes: string;
}

export interface PackageVersion {
  revision: number;
  id: number;
  version_number: number;
  status: "draft" | "active" | "retired";
  is_editable: boolean;
  cable_waste_factor: string;
  cable_termination_buffer_m: string;
  battery_depth_of_discharge: string | null;
  notes: string;
  reviewed_by_name: string;
  reviewed_at: string | null;
  lines: PackageLine[];
}

export interface PackageTemplate {
  id: number;
  kind: string;
  capacity_kw: string | null;
  name: string;
  active_version_number: number | null;
  has_draft: boolean;
}

export interface PackageTemplateDetail extends PackageTemplate {
  versions: PackageVersion[];     // newest first
}
