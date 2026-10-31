/* Fulfilment states, mapped to the six tones from design.md section 7. */

import type { StatusInfo } from "../../components/status";

export const FULFILMENT_STATUSES: Record<string, StatusInfo> = {
  pending: { label: "Pending", tone: "neutral" },
  reserved: { label: "Reserved", tone: "active" },
  packed: { label: "Packed", tone: "waiting" },
  dispatched: { label: "Dispatched", tone: "waiting" },
  delivered: { label: "Delivered", tone: "done" },
  // Red: nobody else will clear a shortage on its own.
  blocked: { label: "Short of stock", tone: "blocked" },
};
