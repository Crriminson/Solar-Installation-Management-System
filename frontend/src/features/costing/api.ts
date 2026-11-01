/* Costs and payables (F14). Money moves are Finance's; the server checks. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";

/* A list URL for one page. Page one is the default and is left off. */
function paged(path: string, page: number) {
  if (page <= 1) return path;
  return `${path}${path.includes("?") ? "&" : "?"}page=${page}`;
}

export interface JobCost {
  order: number;
  reference: string;
  status: string;
  net_revenue_excl_tax: string;
  quoted_cost_excl_tax: string;
  quoted_margin: string;
  equipment_cost: string;
  labour_cost: string;
  labour_hours: string;
  project_expenses: string;
  operational_margin: string;
  service_cost: string;
  repair_revenue_excl_tax: string;
  lifetime_contribution: string;
}

export interface TechnicianSummary {
  technician: number;
  name: string;
  current_rate: string | null;
  hours: string;
  accrued: string;
  paid: string;
  outstanding: string;
}

export interface TimeEntry {
  id: number;
  job: number;
  technician: number;
  technician_name: string;
  work_date: string;
  hours: string;
  rate_per_hour?: string;
  cost_amount?: string;
  note: string;
  is_reversed: boolean;
  reversed_reason: string;
}

export interface Expense {
  id: number;
  order: number;
  description: string;
  amount_excl_tax: string;
  incurred_on: string;
  is_reversed: boolean;
  reversed_reason: string;
}

export interface TechnicianPayment {
  id: number;
  technician: number;
  technician_name: string;
  amount: string;
  paid_on: string;
  reference: string;
  is_reversed: boolean;
  reversed_reason: string;
}

export interface SupplierPayment {
  id: number;
  purchase_order: number;
  amount: string;
  paid_on: string;
  reference: string;
  is_reversed: boolean;
  reversed_reason: string;
}

export function fetchJobCost(orderId: number) {
  return apiGet<JobCost>(`costing/orders/${orderId}/`);
}

export function fetchTechnicianSummaries() {
  return apiGet<TechnicianSummary[]>("costing/technicians/");
}

export function setRate(data: Record<string, unknown>) {
  return apiPost<unknown>("costing/rates/", data);
}

export function fetchTime(jobId: number, page = 1) {
  return apiGet<Paginated<TimeEntry>>(paged(`costing/time/?job=${jobId}`, page));
}

export function recordTime(data: Record<string, unknown>) {
  return apiPost<TimeEntry>("costing/time/", data);
}

export function reverseTime(id: number, reason: string) {
  return apiPost<TimeEntry>(`costing/time/${id}/reverse/`, { reason });
}

export function fetchTechnicianPayments(page = 1) {
  return apiGet<Paginated<TechnicianPayment>>(paged("costing/technician-payments/", page));
}

export function payTechnician(data: Record<string, unknown>) {
  return apiPost<TechnicianPayment>("costing/technician-payments/", data);
}

export function reverseTechnicianPayment(id: number, reason: string) {
  return apiPost<TechnicianPayment>(`costing/technician-payments/${id}/reverse/`, { reason });
}

export function fetchExpenses(orderId: number, page = 1) {
  return apiGet<Paginated<Expense>>(paged(`costing/expenses/?order=${orderId}`, page));
}

export function recordExpense(data: Record<string, unknown>) {
  return apiPost<Expense>("costing/expenses/", data);
}

export function reverseExpense(id: number, reason: string) {
  return apiPost<Expense>(`costing/expenses/${id}/reverse/`, { reason });
}

export function fetchSupplierPayments(purchaseId: number, page = 1) {
  return apiGet<Paginated<SupplierPayment>>(
    paged(`costing/supplier-payments/?purchase_order=${purchaseId}`, page));
}

export function paySupplier(data: Record<string, unknown>) {
  return apiPost<SupplierPayment>("costing/supplier-payments/", data);
}

export function reverseSupplierPayment(id: number, reason: string) {
  return apiPost<SupplierPayment>(`costing/supplier-payments/${id}/reverse/`, { reason });
}

export function recordSupplierInvoice(purchaseId: number, reference: string, amount: string) {
  return apiPost<unknown>(`costing/purchases/${purchaseId}/invoice/`, { reference, amount });
}
