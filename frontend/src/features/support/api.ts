/* Support calls. Every state change sends the revision on screen. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { CustomerEquipment, LookupResult, Ticket, TicketRow } from "./types";

export function fetchTickets(params: URLSearchParams) {
  return apiGet<Paginated<TicketRow>>(`tickets/?${params}`);
}

export function fetchTicket(id: string) {
  return apiGet<Ticket>(`tickets/${id}/`);
}

export function lookup(term: string) {
  return apiGet<LookupResult>(`support/lookup/?q=${encodeURIComponent(term)}`);
}

export function fetchCustomerEquipment(id: string) {
  return apiGet<CustomerEquipment>(`support/customers/${id}/`);
}

export function raiseTicket(data: Record<string, unknown>) {
  return apiPost<Ticket>("tickets/raise/", data);
}

export function ticketAction(ticket: Ticket, action: string, data: Record<string, unknown>) {
  return apiPost<Ticket>(`tickets/${ticket.id}/${action}/`, { revision: ticket.revision, ...data });
}

export function bookVisit(ticket: Ticket, data: Record<string, unknown>) {
  return apiPost<unknown>(`tickets/${ticket.id}/visit/`, data);
}

export function reviewAsset(ticket: Ticket, asset: number, data: Record<string, string>) {
  return apiPost<Ticket>(`tickets/${ticket.id}/review/`, {
    revision: ticket.revision, asset, ...data,
  });
}

export function uploadTicketPhoto(ticket: Ticket, image: File, caption: string) {
  const form = new FormData();
  form.append("image", image);
  form.append("caption", caption);
  return apiPost<unknown>(`tickets/${ticket.id}/photos/`, form);
}
