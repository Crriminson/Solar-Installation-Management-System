/* Scheduling records (F10). */

export interface Assignment {
  id: number;
  technician: number;
  technician_name: string;
  username: string;
  is_lead: boolean;
}

export interface ScheduleChange {
  id: number;
  previous_starts_at: string;
  previous_ends_at: string;
  reason: string;
  changed_by: number;
  changed_by_name: string;
  changed_at: string;
}

export interface Job {
  id: number;
  kind: "survey" | "installation" | "service";
  status: "scheduled" | "in_progress" | "awaiting_acceptance" | "completed" | "cancelled";
  site?: number;
  site_address: string;
  customer_name: string;
  order?: number | null;
  order_reference?: string;
  survey?: number | null;
  starts_at: string;
  ends_at: string;
  notes: string;
  is_blocked: boolean;
  blocked_reason: string;
  blocked_owner?: number | null;
  cancelled_reason?: string;
  revision: number;
  created_at?: string;
  assignments: Assignment[];
  schedule_changes?: ScheduleChange[];
}
