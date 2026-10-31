/* Reading where a survey stands from its latest revision. */

import {
  REVISION_STATUSES,
  SURVEY_NOT_STARTED,
  type StatusInfo,
} from "../../components/status";
import type { Survey } from "./types";

export function latestStatus(survey: Survey): StatusInfo {
  const latest = survey.revisions[0];
  return latest ? REVISION_STATUSES[latest.status] : SURVEY_NOT_STARTED;
}

/* Who holds this survey now. */
export function waitingOn(survey: Survey) {
  // A new revision of an approved survey changes nothing until approved.
  const latest = survey.revisions[0];
  if (survey.is_approved && latest?.status !== "approved") {
    return "The approved revision stays in use until this one is approved";
  }

  switch (latest?.status) {
    case "draft":
      return "Waiting on the technician to submit it";
    case "submitted":
      return "Waiting on an operations manager";
    case "changes_requested":
      return "Waiting on the technician to correct and resubmit this revision";
    case "approved":
      return "Approved. A quotation can be built from this revision";
    case "rejected":
      return "Rejected";
    default:
      return "Waiting on the site visit";
  }
}
