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
  switch (survey.revisions[0]?.status) {
    case "draft":
      return "Waiting on the technician to submit it";
    case "submitted":
      return "Waiting on an operations manager";
    case "changes_requested":
      return "Waiting on a new revision from the technician";
    case "approved":
      return "Approved. A quotation can be built from this revision";
    case "rejected":
      return "Rejected";
    default:
      return "Waiting on the site visit";
  }
}
