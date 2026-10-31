/* Job states, mapped to the six tones from design.md section 7. */

import type { StatusInfo } from "../../components/status";

export const JOB_STATUSES: Record<string, StatusInfo> = {
  scheduled: { label: "Scheduled", tone: "neutral" },
  in_progress: { label: "In progress", tone: "active" },
  awaiting_acceptance: { label: "Awaiting customer", tone: "waiting" },
  completed: { label: "Completed", tone: "done" },
  cancelled: { label: "Cancelled", tone: "closed" },
};

export const JOB_KINDS: Record<string, string> = {
  survey: "Site survey",
  installation: "Installation",
  service: "Service visit",
};
