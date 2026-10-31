/* Quotation requests retain a retry key until the user changes the operation. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { Quotation } from "./types";

export function fetchQuotations(params: URLSearchParams) {
  return apiGet<Paginated<Quotation>>(`quotations/?${params}`);
}

export function fetchQuotation(id: string) {
  return apiGet<Quotation>(`quotations/${id}/`);
}

export function generateQuotation(data: Record<string, unknown>) {
  return apiPost<Quotation>("quotations/generate/", data);
}

export function quotationAction(quotation: Quotation, action: string, key: string, reason: string) {
  return apiPost<Quotation>(`quotations/${quotation.id}/${action}/`, {
    revision: quotation.revision, idempotency_key: key, reason,
  });
}
