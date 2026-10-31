/*
  Enquiry API calls.

  Screens import these instead of calling fetch, so the URLs live in one
  place.
*/

import { apiGet, apiPost, apiRequest } from "../../api/client";
import type {
  ContactLogEntry,
  EnquiryCreated,
  EnquiryListItem,
  EnquiryStatus,
  Paginated,
} from "./types";

/* Submits the enquiry form, which may carry an electricity bill. */
export function submitEnquiry(values: FormData) {
  return apiPost<EnquiryCreated>("enquiries/submit/", values);
}

/* Which slice of the queue to show. */
export interface QueueFilters {
  search?: string;
  status?: string;
  unassigned?: boolean;
  overdue?: boolean;
}

/* Loads the sales queue. Filtering happens on the server. */
export function fetchEnquiries(filters: QueueFilters) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.status) params.set("status", filters.status);
  if (filters.unassigned) params.set("unassigned", "true");
  if (filters.overdue) params.set("overdue", "true");

  const query = params.toString();
  return apiGet<Paginated<EnquiryListItem>>(
    `enquiries/${query ? `?${query}` : ""}`,
  );
}

/* --- follow-up actions (F02) --- */

export function fetchContactLog(enquiryId: number) {
  return apiGet<Paginated<ContactLogEntry>>(`enquiries/${enquiryId}/contacts/`);
}

export function recordContact(
  enquiryId: number,
  entry: {
    channel: string;
    contacted_at: string;
    summary: string;
    reached_customer: boolean;
  },
) {
  return apiPost<ContactLogEntry>(`enquiries/${enquiryId}/contacts/`, entry);
}

export function assignEnquiry(
  enquiryId: number,
  data: { owner: number; next_action: string; next_action_due?: string | null },
) {
  return apiRequest<EnquiryListItem>(`enquiries/${enquiryId}/assign/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function changeStatus(
  enquiryId: number,
  data: {
    status: EnquiryStatus;
    reason?: string;
    next_action?: string;
    next_action_due?: string | null;
  },
) {
  return apiPost<EnquiryListItem>(`enquiries/${enquiryId}/status/`, data);
}
