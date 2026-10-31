/* Purchasing and stock records (F08). */

export interface Supplier {
  id: number;
  name: string;
  contact_name: string;
  phone: string;
  email: string;
  gstin: string;
  is_active: boolean;
  created_at: string;
}

export interface PurchaseLine {
  id: number;
  product: number;
  sku: string;
  name: string;
  unit: string;
  tracking_method: "serialized" | "bulk" | "service";
  quantity: string;
  received_quantity: string;
  outstanding_quantity: string;
  unit_cost: string;
}

export interface PurchaseOrder {
  id: number;
  reference: string;
  supplier: number;
  supplier_name: string;
  status: "draft" | "placed" | "part_received" | "received" | "cancelled";
  supplier_invoice_reference: string;
  supplier_invoice_amount: string | null;
  supplier_payment_status: "unpaid" | "part_paid" | "paid";
  placed_on: string | null;
  expected_on: string | null;
  revision: number;
  created_at: string;
  lines: PurchaseLine[];
}

export interface SerializedUnit {
  id: number;
  asset_id: string;
  serial_number: string;
  product: number;
  sku: string;
  name: string;
  status: string;
  on_hand: boolean;
  location: string;
  acquisition_cost: string;
  goods_receipt: number;
  order: number | null;
  customer: number | null;
  site: number | null;
  created_at: string;
}

export interface BatchLot {
  id: number;
  batch_id: string;
  product: number;
  sku: string;
  name: string;
  quantity: string;
  unit: string;
  status: string;
  on_hand: boolean;
  location: string;
  unit_cost: string;
  goods_receipt: number;
  order: number | null;
  created_at: string;
}

export interface StockMovement {
  id: number;
  unit: number | null;
  asset_id: string;
  lot: number | null;
  batch_id: string;
  reason: string;
  from_status: string;
  to_status: string;
  quantity: string;
  order: number | null;
  note: string;
  moved_by: number;
  moved_by_name: string;
  moved_at: string;
}
