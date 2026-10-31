/* Survey API calls (F03). */

import { apiGet, apiPatch, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type {
  MeasurementValues,
  ReviewDecision,
  Survey,
  SurveyPhoto,
  SurveyRevision,
} from "./types";

export interface SurveyFilters {
  approved?: boolean;
  search?: string;
  pending?: boolean;
  open?: boolean;
  page?: number;
}

export function fetchSurveys(filters: SurveyFilters) {
  const params = new URLSearchParams();
  if (filters.approved) params.set("approved", "true");
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

export function submitRevision(revisionId: number, revision: number) {
  return apiPost<SurveyRevision>(`revisions/${revisionId}/submit/`, { revision });
}

export function reviewRevision(
  revisionId: number,
  data: { decision: ReviewDecision; notes: string; revision: number },
) {
  return apiPost<SurveyRevision>(`revisions/${revisionId}/review/`, data);
}

export function editRevision(revisionId: string, values: Record<string, unknown>) {
  return apiPatch<SurveyRevision>(`revisions/${revisionId}/`, values);
}

export function assignSurvey(survey: Survey, technician: number) {
  return apiPost<Survey>(`surveys/${survey.id}/assign/`, { assigned_to: technician, revision: survey.revision });
}

export function addPhoto(revisionId: number, photo: File, caption: string) {
  const data = new FormData();
  data.append("image", photo);
  data.append("caption", caption);
  return apiPost<SurveyPhoto>(`revisions/${revisionId}/photos/`, data);
}
