/* Quotation requests retain a retry key until the user changes the operation. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { Presentation, Quotation } from "./types";

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

/* F06: the restricted document the customer reads before signing. */
export function fetchPresentation(id: string) {
  return apiGet<Presentation>(`quotations/${id}/present/`);
}

/* F06: a supervised signature. Multipart, because it carries the image. */
export function acceptQuotation(id: string, revision: number, key: string,
                                customerName: string, signature: Blob) {
  const form = new FormData();
  form.append("revision", String(revision));
  form.append("idempotency_key", key);
  form.append("customer_name", customerName);
  form.append("signature", signature, "signature.png");
  return apiPost<Quotation>(`quotations/${id}/accept/`, form);
}
