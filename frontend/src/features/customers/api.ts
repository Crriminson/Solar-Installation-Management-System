/* F01: customers are made by enquiries, so these are read only. */

import { apiGet } from "../../api/client";
import type { CustomerRecord, CustomerRow } from "./types";

export interface Paginated<T> {
  count: number;
  results: T[];
}

export function fetchCustomers(search: string, page: number) {
  const params = new URLSearchParams({ page: String(page) });
  if (search) params.set("search", search);
  return apiGet<Paginated<CustomerRow>>(`customers/?${params}`);
}

export function fetchCustomer(id: string) {
  return apiGet<CustomerRecord>(`customers/${id}/`);
}
