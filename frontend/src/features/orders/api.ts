/* Order and ledger calls. Every write sends the revision on screen. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { Order, Payment } from "./types";

export function fetchOrders(params: URLSearchParams) {
  return apiGet<Paginated<Order>>(`orders/?${params}`);
}

export function fetchOrder(id: string) {
  return apiGet<Order>(`orders/${id}/`);
}

export function confirmOrder(quotationId: number) {
  return apiPost<Order>("orders/confirm/", { quotation: quotationId });
}

export function cancelOrder(order: Order, reason: string) {
  return apiPost<Order>(`orders/${order.id}/cancel/`, {
    revision: order.revision, reason,
  });
}

export function issueBalanceInvoice(order: Order) {
  return apiPost<Order>(`orders/${order.id}/balance-invoice/`, {});
}

export function recordPayment(orderId: number, data: Record<string, unknown>) {
  return apiPost<Payment>(`orders/${orderId}/payments/`, data);
}

export function clearPayment(payment: Payment) {
  return apiPost<Payment>(`payments/${payment.id}/clear/`, {
    revision: payment.revision,
  });
}

export function reversePayment(payment: Payment, reason: string) {
  return apiPost<Payment>(`payments/${payment.id}/reverse/`, {
    revision: payment.revision, reason,
  });
}

export function allocatePayment(payment: Payment, invoiceId: number, amount: string) {
  return apiPost<Payment>(`payments/${payment.id}/allocate/`, {
    invoice: invoiceId, amount,
  });
}
