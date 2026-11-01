/* F19 over the wire. Documents are generated, never uploaded. */

import { apiGet, apiPost } from "../../api/client";

export type DocumentKind = "quotation" | "invoice" | "receipt" | "handover";

export interface GeneratedDocument {
  id: number;
  kind: DocumentKind;
  kind_label: string;
  reference: string;
  revision: number;
  content_hash: string;
  generated_at: string;
  generated_by_name: string;
}

/* The query parameter is the record column, which differs from the
   document kind for a receipt (a payment) and a handover (a report). */
const RECORD_FIELD: Record<DocumentKind, string> = {
  quotation: "quotation",
  invoice: "invoice",
  receipt: "payment",
  handover: "installation",
};

export function fetchDocuments(kind: DocumentKind, recordId: number) {
  return apiGet<{ results: GeneratedDocument[] }>(
    `documents/?kind=${kind}&${RECORD_FIELD[kind]}=${recordId}`,
  );
}

export function generateDocument(kind: DocumentKind, recordId: number) {
  return apiPost<GeneratedDocument>(`documents/${kind}/${recordId}/generate/`, {});
}

export function downloadUrl(documentId: number) {
  return `/api/v1/documents/${documentId}/download/`;
}
