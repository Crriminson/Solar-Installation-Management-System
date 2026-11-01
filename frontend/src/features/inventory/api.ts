/* Purchasing and stock calls. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { BatchLot, PurchaseOrder, SerializedUnit, StockMovement, Supplier } from "./types";

/* The printable barcode labels for a purchase order's or an order's goods. */
export function stockLabelsUrl(target: { purchase_order: number } | { order: number }) {
  return `/api/v1/stock/labels/?${new URLSearchParams(
    Object.entries(target).map(([key, value]) => [key, String(value)]))}`;
}

export function fetchSuppliers(params: URLSearchParams) {
  return apiGet<Paginated<Supplier>>(`suppliers/?${params}`);
}

export function createSupplier(data: Record<string, unknown>) {
  return apiPost<Supplier>("suppliers/", data);
}

export function fetchPurchaseOrders(params: URLSearchParams) {
  return apiGet<Paginated<PurchaseOrder>>(`purchase-orders/?${params}`);
}

export function fetchPurchaseOrder(id: string) {
  return apiGet<PurchaseOrder>(`purchase-orders/${id}/`);
}

export function createPurchaseOrder(data: Record<string, unknown>) {
  return apiPost<PurchaseOrder>("purchase-orders/create/", data);
}

export function placePurchaseOrder(purchase: PurchaseOrder) {
  return apiPost<PurchaseOrder>(`purchase-orders/${purchase.id}/place/`, {
    revision: purchase.revision,
  });
}

export function cancelPurchaseOrder(purchase: PurchaseOrder, reason: string) {
  return apiPost<PurchaseOrder>(`purchase-orders/${purchase.id}/cancel/`, {
    revision: purchase.revision, reason,
  });
}

/* Each row is one purchase order line being booked in. */
export interface ReceiptLine {
  line: number;
  serial_numbers?: string[];
  batch_id?: string;
  quantity?: string;
}

export function receiveGoods(purchaseId: number, data: {
  received_on: string;
  delivery_note_reference: string;
  notes: string;
  lines: ReceiptLine[];
}) {
  return apiPost<{ id: number; reference: string }>(
    `purchase-orders/${purchaseId}/receive/`, data,
  );
}

export function fetchUnits(params: URLSearchParams) {
  return apiGet<Paginated<SerializedUnit>>(`stock/units/?${params}`);
}

export function fetchLots(params: URLSearchParams) {
  return apiGet<Paginated<BatchLot>>(`stock/lots/?${params}`);
}

export function fetchMovements(params: URLSearchParams) {
  return apiGet<Paginated<StockMovement>>(`stock/movements/?${params}`);
}
