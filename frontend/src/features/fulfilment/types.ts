/* Warehouse fulfilment records (F09). */

export interface ScanEvent {
  id: number;
  unit: number | null;
  asset_id: string;
  serial_number: string;
  lot: number | null;
  batch_id: string;
  quantity: string;
  entered_manually: boolean;
  manual_reason: string;
  scanned_by: number;
  scanned_by_name: string;
  scanned_at: string;
}

export interface PackingLine {
  id: number;
  product: number;
  sku: string;
  description: string;
  unit: string;
  tracking_method: "serialized" | "bulk" | "service";
  required_quantity: string;
  reserved_quantity: string;
  packed_quantity: string;
  outstanding_quantity: string;
  is_complete: boolean;
  scans: ScanEvent[];
}

export interface Fulfilment {
  id: number;
  order: number;
  order_reference: string;
  customer_name: string;
  status: "pending" | "reserved" | "packed" | "dispatched" | "delivered" | "blocked";
  blocked_reason: string;
  is_complete: boolean;
  dispatch_allowed: boolean;
  carrier_reference: string;
  dispatched_at: string | null;
  delivered_at: string | null;
  delivery_recorded_at: string | null;
  received_by_name: string;
  delivery_notes: string;
  revision: number;
  created_at: string;
  lines: PackingLine[];
}
