/* Ticket states and wording, mapped to the tones from design.md section 7. */

import type { StatusInfo } from "../../components/status";

export const TICKET_STATUSES: Record<string, StatusInfo> = {
  new: { label: "New", tone: "neutral" },
  diagnosed: { label: "Diagnosed", tone: "active" },
  in_progress: { label: "In progress", tone: "active" },
  awaiting_confirmation: { label: "Awaiting customer", tone: "waiting" },
  closed: { label: "Closed", tone: "closed" },
};

/* Review is red: nothing can move until an authorized person rules on it. */
export const ASSESSMENTS: Record<string, StatusInfo> = {
  covered: { label: "Covered", tone: "done" },
  not_covered: { label: "Not covered", tone: "waiting" },
  review: { label: "Needs review", tone: "blocked" },
};

export const ESTIMATE_STATUSES: Record<string, StatusInfo> = {
  pending: { label: "Awaiting approval", tone: "waiting" },
  approved: { label: "Approved", tone: "done" },
  declined: { label: "Declined", tone: "closed" },
  superseded: { label: "Superseded", tone: "closed" },
};

export const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
];

export const DISPOSITIONS = [
  { value: "quarantined", label: "Quarantined for inspection" },
  { value: "returned", label: "Returned" },
];
