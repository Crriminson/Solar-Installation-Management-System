/* Order and payment states, mapped to the six tones from design.md section 7. */

import type { StatusInfo } from "../../components/status";

export const ORDER_STATUSES: Record<string, StatusInfo> = {
  confirmed: { label: "Confirmed", tone: "active" },
  delivered: { label: "Delivered", tone: "waiting" },
  completed: { label: "Completed", tone: "done" },
  cancelled: { label: "Cancelled", tone: "closed" },
};

/* Pending is "waiting" rather than "done": the money has not arrived. */
export const PAYMENT_STATUSES: Record<string, StatusInfo> = {
  pending: { label: "Pending", tone: "waiting" },
  cleared: { label: "Cleared", tone: "done" },
  reversed: { label: "Reversed", tone: "closed" },
};

export const INVOICE_KINDS: Record<string, string> = {
  advance: "Advance",
  balance: "Balance",
  full: "Full amount",
  zero_charge: "Zero charge",
};

export const PAYMENT_METHODS = [
  { value: "upi", label: "UPI" },
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "cash", label: "Cash" },
  { value: "cheque", label: "Cheque" },
  { value: "card", label: "Card" },
];
