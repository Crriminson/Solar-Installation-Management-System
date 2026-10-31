/* Warranty states and wording, mapped to the tones from design.md section 7. */

import type { StatusInfo } from "../../components/status";

const MONTHS_PER_YEAR = 12;

/* Expired is Closed, not Blocked: nobody has to act because time passed. */
export const WARRANTY_STATUSES: Record<string, StatusInfo> = {
  in_cover: { label: "In cover", tone: "done" },
  expired: { label: "Expired", tone: "closed" },
  replaced: { label: "Replaced", tone: "closed" },
};

export const COVERAGE_BASES: Record<string, string> = {
  delivery: "From delivery",
  inherited: "Inherited from the replaced unit",
  fresh: "Fresh period on replacement",
};

/* 24 months reads as "2 years", which is how the policy is sold. */
export function describeTerm(months: number) {
  if (months % MONTHS_PER_YEAR !== 0) {
    return `${months} ${months === 1 ? "month" : "months"}`;
  }
  const years = months / MONTHS_PER_YEAR;
  return `${years} ${years === 1 ? "year" : "years"}`;
}
