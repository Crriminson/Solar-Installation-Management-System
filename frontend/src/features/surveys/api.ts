/* Survey API calls (F03). */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type {
  MeasurementValues,
  ReviewDecision,
  Survey,
  SurveyPhoto,
  SurveyRevision,
} from "./types";

export interface SurveyFilters {
  search?: string;
  pending?: boolean;
  open?: boolean;
  page?: number;
}

export function fetchSurveys(filters: SurveyFilters) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.pending) params.set("pending", "true");
  if (filters.open) params.set("open", "true");
  if (filters.page && filters.page > 1) params.set("page", String(filters.page));

  const query = params.toString();
  return apiGet<Paginated<Survey>>(`surveys/${query ? `?${query}` : ""}`);
}

export function fetchSurvey(surveyId: string) {
  return apiGet<Survey>(`surveys/${surveyId}/`);
}

/* Safe to call twice: an enquiry has one survey. */
export function startSurvey(enquiryId: number) {
  return apiPost<Survey>("surveys/start/", { enquiry: enquiryId });
}

export function createRevision(surveyId: string, values: Partial<MeasurementValues>) {
  return apiPost<SurveyRevision>(`surveys/${surveyId}/revisions/`, values);
}

export function submitRevision(revisionId: number) {
  return apiPost<SurveyRevision>(`revisions/${revisionId}/submit/`);
}

export function reviewRevision(
  revisionId: number,
  data: { decision: ReviewDecision; notes: string },
) {
  return apiPost<SurveyRevision>(`revisions/${revisionId}/review/`, data);
}

export function addPhoto(revisionId: number, photo: File, caption: string) {
  const data = new FormData();
  data.append("image", photo);
  data.append("caption", caption);
  return apiPost<SurveyPhoto>(`revisions/${revisionId}/photos/`, data);
}
