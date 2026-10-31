/*
  Enquiry API calls.

  Screens import these instead of calling fetch, so the URLs live in one
  place.
*/

import { apiGet, apiPatch, apiPost } from "../../api/client";
import type {
  ContactLogEntry,
  EnquiryCreated,
  EnquiryListItem,
  EnquiryStatus,
  Paginated,
  StaffMember,
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
  page?: number;
}

/* Loads the sales queue. Filtering happens on the server. */
export function fetchEnquiries(filters: QueueFilters) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.status) params.set("status", filters.status);
  if (filters.unassigned) params.set("unassigned", "true");
  if (filters.overdue) params.set("overdue", "true");
  if (filters.page && filters.page > 1) params.set("page", String(filters.page));

  const query = params.toString();
  return apiGet<Paginated<EnquiryListItem>>(
    `enquiries/${query ? `?${query}` : ""}`,
  );
}

/* Where the browser fetches an enquiry's uploaded bill. */
export function billDownloadUrl(enquiryId: number) {
  return `/api/v1/enquiries/${enquiryId}/bill/`;
}

/* --- follow-up actions (F02) --- */

/* Everyone a lead can be given to. */
export function fetchStaff() {
  return apiGet<StaffMember[]>("staff/");
}

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
  return apiPatch<EnquiryListItem>(`enquiries/${enquiryId}/assign/`, data);
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


export function reviewDuplicate(enquiry: EnquiryListItem, decision: string, reason: string) {
  return apiPost<EnquiryListItem>(`enquiries/${enquiry.id}/duplicate-review/`, { revision: enquiry.revision, decision, reason });
}
