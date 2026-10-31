/* Warranty lookups. There are no writes: cover comes from a delivery. */

import { apiGet } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { OrderWarranties, Warranty, WarrantyDetail } from "./types";

export function fetchWarranties(params: URLSearchParams) {
  return apiGet<Paginated<Warranty>>(`warranties/?${params}`);
}

export function fetchWarranty(id: string) {
  return apiGet<WarrantyDetail>(`warranties/${id}/`);
}

export function fetchOrderWarranties(orderId: number) {
  return apiGet<OrderWarranties>(`orders/${orderId}/warranties/`);
}
