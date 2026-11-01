/*
  F16 over the wire.

  The public calls carry no session: the token in the path is the whole
  authorisation, which is why they go straight to fetch rather than
  through the signed-in client.
*/

import { apiGet, apiPost } from "../../api/client";
import type { Presentation } from "../quotations/types";

export type LinkState = "open" | "spent" | "expired" | "revoked" | "superseded";

export interface PublicLink {
  purpose: "sign_quotation" | "confirm_ticket";
  state: LinkState;
  expires_at: string;
  document?: Presentation;
  ticket?: { reference: string; status: string; fault: string };
}

export interface Binding {
  id: number;
  customer: number;
  customer_name: string;
  chat_id: string;
  chat_name: string;
  linked_at: string;
  revoked_at: string | null;
  revoked_reason: string;
  is_live: boolean;
}

export interface InboxMessage {
  id: number;
  chat_id: string;
  text: string;
  received_at: string;
  customer_name: string;
}

/* ---------- staff ---------- */

export function issueLinkToken(customerId: number) {
  return apiPost<{ token: string; deep_link: string; expires_at: string }>(
    `customers/${customerId}/telegram-token/`,
    {},
  );
}

export function fetchBindings(customerId?: number) {
  const query = customerId ? `?customer=${customerId}` : "";
  return apiGet<{ results: Binding[] }>(`telegram/bindings/${query}`);
}

export function revokeBinding(id: number, reason: string) {
  return apiPost<Binding>(`telegram/bindings/${id}/revoke/`, { reason });
}

export function sendQuotation(quotationId: number) {
  return apiPost<{ queued: boolean }>(`quotations/${quotationId}/send/`, {});
}

export function requestConfirmation(ticketId: number) {
  return apiPost<{ queued: boolean }>(`tickets/${ticketId}/request-confirmation/`, {});
}

export function fetchInbox() {
  return apiGet<{ results: InboxMessage[] }>("telegram/inbox/");
}

/* ---------- public, no session ---------- */

const PUBLIC_BASE = "/api/v1/public/links";

export async function fetchPublicLink(token: string) {
  const response = await fetch(`${PUBLIC_BASE}/${token}/`);
  if (!response.ok) throw new Error("This link is not valid.");
  return (await response.json()) as PublicLink;
}

/* Multipart, because signing carries the signature image. */
export async function submitPublicLink(
  token: string,
  fields: Record<string, string>,
  signature?: Blob,
) {
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) form.append(key, value);
  if (signature) form.append("signature", signature, "signature.png");

  const response = await fetch(`${PUBLIC_BASE}/${token}/accept/`, {
    method: "POST",
    body: form,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "That did not go through. Please try again.",
    );
  }
  return data;
}
