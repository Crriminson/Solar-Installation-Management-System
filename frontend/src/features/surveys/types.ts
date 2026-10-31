/* Shapes the survey API sends and receives (F03). */

export type RevisionStatus =
  | "draft"
  | "submitted"
  | "changes_requested"
  | "approved"
  | "rejected"
  | "superseded";

export type ReviewDecision = "approved" | "changes_requested" | "rejected";

export interface SurveyPhoto {
  id: number;
  url: string;
  caption: string;
  uploaded_at: string;
}

/* What the technician records. Empty strings mean left blank. */
export interface MeasurementValues {
  roof_type: string;
  roof_length_m: string;
  roof_width_m: string;
  usable_area_sqm: string;
  orientation: string;
  tilt_degrees: string;
  shading_notes: string;
  cable_distance_m: string;
  cable_route_notes: string;
  site_access_notes: string;
  grid_connection_number: string;
  sanctioned_load_kw: string;
  grid_suitable: string;
  grid_notes: string;
  recommended_system_type: string;
  recommended_capacity_kw: string;
  critical_load_kw: string;
  backup_duration_hours: string;
  surveyed_at: string;
}

export interface SurveyRevision {
  revision: number;
  id: number;
  revision_number: number;
  status: RevisionStatus;
  is_editable: boolean;
  roof_type: string;
  roof_length_m: string;
  roof_width_m: string;
  usable_area_sqm: string;
  orientation: string;
  tilt_degrees: string;
  shading_notes: string;
  cable_distance_m: string;
  cable_route_notes: string;
  site_access_notes: string;
  grid_connection_number: string;
  sanctioned_load_kw: string | null;
  grid_suitable: boolean;
  grid_notes: string;
  recommended_system_type: string;
  recommended_capacity_kw: string;
  critical_load_kw: string | null;
  backup_duration_hours: string | null;
  surveyed_at: string;
  surveyed_by_name: string;
  submitted_at: string | null;
  reviewed_by_name: string;
  reviewed_at: string | null;
  review_notes: string;
  photos: SurveyPhoto[];
}

export interface Survey {
  site_state: string;
  revision: number;
  assigned_to: number | null;
  id: number;
  enquiry: number;
  enquiry_reference: string;
  customer_name: string;
  is_approved: boolean;
  revisions: SurveyRevision[];     // newest first
  created_at: string;
}
