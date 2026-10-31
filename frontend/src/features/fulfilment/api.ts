/* Warehouse fulfilment calls. Every write sends the revision on screen. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { Fulfilment, ScanEvent } from "./types";

export function fetchFulfilments(params: URLSearchParams) {
  return apiGet<Paginated<Fulfilment>>(`fulfilments/?${params}`);
}

export function fetchFulfilment(id: string) {
  return apiGet<Fulfilment>(`fulfilments/${id}/`);
}

export function openFulfilment(orderId: number) {
  return apiPost<Fulfilment>("fulfilments/open/", { order: orderId });
}

export function reserveStock(fulfilment: Fulfilment) {
  return apiPost<Fulfilment>(`fulfilments/${fulfilment.id}/reserve/`, {});
}

export interface ScanInput {
  code: string;
  quantity?: string;
  entered_manually?: boolean;
  manual_reason?: string;
}

export function scanItem(fulfilmentId: number, input: ScanInput) {
  return apiPost<ScanEvent>(`fulfilments/${fulfilmentId}/scan/`, input);
}

export function closePacking(fulfilment: Fulfilment) {
  return apiPost<Fulfilment>(`fulfilments/${fulfilment.id}/close/`, {
    revision: fulfilment.revision,
  });
}

export function dispatchOrder(fulfilment: Fulfilment, carrierReference: string) {
  return apiPost<Fulfilment>(`fulfilments/${fulfilment.id}/dispatch/`, {
    revision: fulfilment.revision, carrier_reference: carrierReference,
  });
}

export function recordDelivery(fulfilment: Fulfilment, data: {
  delivered_at: string; received_by_name: string; delivery_notes: string;
}) {
  return apiPost<Fulfilment>(`fulfilments/${fulfilment.id}/deliver/`, {
    revision: fulfilment.revision, ...data,
  });
}
