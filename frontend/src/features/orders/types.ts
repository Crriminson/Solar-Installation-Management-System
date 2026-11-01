/* Orders carry the agreed terms and the money recorded against them (F07). */

export interface Allocation {
  id: number;
  invoice: number;
  invoice_reference: string;
  amount: string;
  created_at: string;
}

export interface Invoice {
  id: number;
  reference: string;
  kind: "advance" | "balance" | "full" | "zero_charge";
  amount: string;
  paid_amount: string;
  outstanding: string;
  settled: boolean;
  issued_at: string;
}

export interface Payment {
  id: number;
  kind: "receipt" | "refund";
  amount: string;
  allocated_amount: string;
  unallocated: string;
  method: string;
  external_reference: string;
  status: "pending" | "cleared" | "reversed";
  paid_on: string;
  recorded_at: string;
  recorded_by: number;
  recorded_by_name: string;
  reversed_reason: string;
  revision: number;
  allocations: Allocation[];
}

export interface Order {
  id: number;
  reference: string;
  status: "confirmed" | "delivered" | "completed" | "cancelled";
  quotation: number;
  quotation_reference: string;
  customer: number;
  customer_name: string;
  site: number;
  payment_plan: "advance" | "full";
  gross_payable: string;
  advance_payable: string;
  balance_due_on: string | null;
  cleared_total: string;
  outstanding: string;
  advance_cleared: boolean;
  dispatch_allowed: boolean;
  cancelled_reason: string;
  confirmed_at: string;
  revision: number;
  invoices: Invoice[];
  payments: Payment[];
  /* Where the order went on confirmation: the warehouse and the diary. */
  fulfilment: { id: number; status: string; blocked_reason: string } | null;
  installation: { id: number; status: string; starts_at: string | null } | null;
}
