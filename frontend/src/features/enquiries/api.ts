/*
  Enquiry API calls.

  Screens import these instead of calling fetch, so the URLs live in one
  place.
*/

import { apiGet, apiPost } from "../../api/client";
import type { EnquiryCreated, EnquiryListItem, Paginated } from "./types";

/* Submits the public enquiry form. */
export function submitEnquiry(values: Record<string, unknown>) {
  return apiPost<EnquiryCreated>("enquiries/submit/", values);
}

/* Loads the sales queue, optionally filtered by a search term. */
export function fetchEnquiries(search: string) {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return apiGet<Paginated<EnquiryListItem>>(`enquiries/${query}`);
}
