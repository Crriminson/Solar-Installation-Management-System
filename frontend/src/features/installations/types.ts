/* Installation evidence records (F11). */

export interface ChecklistEntry {
  item: string;
  passed: boolean;
  note?: string;
}

export interface InstalledUnit {
  id: number;
  unit: number;
  asset_id: string;
  serial_number: string;
  sku: string;
  name: string;
  position_note: string;
  recorded_at: string;
}

export interface InstallationPhoto {
  id: number;
  url: string;            // an authorised download, never the storage path
  caption: string;
  uploaded_at: string;
}

export interface Acceptance {
  id: number;
  decision: "accepted" | "refused";
  customer_name: string;
  signature: string | null;
  refusal_reason: string;
  document_revision: number;
  document_content_hash: string;
  witnessed_by: number;
  witnessed_by_name: string;
  decided_at: string;
}

export interface InstallationReport {
  id: number;
  job: number;
  customer_name: string;
  status: "draft" | "submitted" | "accepted" | "refused";
  started_at: string | null;
  finished_at: string | null;
  system_type: string;
  installed_capacity_kw: string | null;
  checklist: ChecklistEntry[];
  generation_test_kw: string | null;
  generation_test_passed: boolean | null;
  generation_test_notes: string;
  notes: string;
  content_hash: string;
  submitted_at: string | null;
  revision: number;
  created_at: string;
  missing_evidence: string[];
  mandatory_checks: string[];
  installed_units: InstalledUnit[];
  photos: InstallationPhoto[];
  acceptance: Acceptance | null;
}
