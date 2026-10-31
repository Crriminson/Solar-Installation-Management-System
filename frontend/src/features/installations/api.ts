/* Installation evidence calls. Photos and signatures go up as multipart. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { Acceptance, InstallationReport, InstalledUnit } from "./types";

export function fetchReports(params: URLSearchParams) {
  return apiGet<Paginated<InstallationReport>>(`installations/?${params}`);
}

export function fetchReport(id: string) {
  return apiGet<InstallationReport>(`installations/${id}/`);
}

export function openReport(jobId: number) {
  return apiPost<InstallationReport>("installations/open/", { job: jobId });
}

export function updateReport(report: InstallationReport, changes: Record<string, unknown>) {
  return apiPost<InstallationReport>(`installations/${report.id}/update/`, {
    revision: report.revision, ...changes,
  });
}

export function addInstalledUnit(reportId: number, code: string, positionNote: string) {
  return apiPost<InstalledUnit>(`installations/${reportId}/units/`, {
    code, position_note: positionNote,
  });
}

export function addPhoto(reportId: number, image: Blob, caption: string) {
  const form = new FormData();
  form.append("image", image, "photo.jpg");
  form.append("caption", caption);
  return apiPost<{ id: number }>(`installations/${reportId}/photos/`, form);
}

export function submitReport(report: InstallationReport) {
  return apiPost<InstallationReport>(`installations/${report.id}/submit/`, {
    revision: report.revision,
  });
}

export function decide(report: InstallationReport, data: {
  decision: "accepted" | "refused";
  customerName: string;
  signature?: Blob | null;
  refusalReason?: string;
}) {
  const form = new FormData();
  form.append("decision", data.decision);
  form.append("document_revision", String(report.revision));
  form.append("customer_name", data.customerName);
  if (data.signature) form.append("signature", data.signature, "signature.png");
  if (data.refusalReason) form.append("refusal_reason", data.refusalReason);
  return apiPost<Acceptance>(`installations/${report.id}/decide/`, form);
}
