/* Purchasing and stock states, mapped to the six tones from design.md section 7. */

import type { StatusInfo } from "../../components/status";

export const PURCHASE_STATUSES: Record<string, StatusInfo> = {
  draft: { label: "Draft", tone: "neutral" },
  placed: { label: "Placed", tone: "waiting" },
  part_received: { label: "Part received", tone: "active" },
  received: { label: "Received", tone: "done" },
  cancelled: { label: "Cancelled", tone: "closed" },
};

/* Quarantined is red: somebody has to decide what happens to it. */
export const STOCK_STATUSES: Record<string, StatusInfo> = {
  available: { label: "Available", tone: "done" },
  reserved: { label: "Reserved", tone: "active" },
  dispatched: { label: "Dispatched", tone: "waiting" },
  delivered: { label: "Delivered", tone: "waiting" },
  installed: { label: "Installed", tone: "done" },
  returned: { label: "Returned", tone: "closed" },
  quarantined: { label: "Quarantined", tone: "blocked" },
};

export const MOVEMENT_REASONS: Record<string, string> = {
  receipt: "Received from supplier",
  reservation: "Reserved for an order",
  release: "Reservation released",
  dispatch: "Dispatched",
  delivery: "Delivered",
  installation: "Installed",
  consumption: "Consumed on a job",
  return: "Returned",
  quarantine: "Quarantined",
  correction: "Counted correction",
};
