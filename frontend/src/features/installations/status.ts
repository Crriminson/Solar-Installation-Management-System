/* Installation report states, mapped to the six tones from design.md section 7. */

import type { StatusInfo } from "../../components/status";

export const REPORT_STATUSES: Record<string, StatusInfo> = {
  draft: { label: "In progress", tone: "active" },
  submitted: { label: "Awaiting customer", tone: "waiting" },
  accepted: { label: "Accepted", tone: "done" },
  // Red, not closed: a refusal is work the crew has to go back and do.
  refused: { label: "Refused", tone: "blocked" },
};
