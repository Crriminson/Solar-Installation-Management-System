/* Shapes the enquiry API sends and receives. */

export type CustomerType = "residential" | "commercial";
export type SystemType = "on_grid" | "off_grid" | "undecided";

/* What the enquiry form posts. Optional fields may be left blank. */
export interface EnquiryFormValues {
  full_name: string;
  phone: string;
  email: string;
  customer_type: string;
  address_line: string;
  city: string;
  state: string;
  pincode: string;
  shadow_free_roof_area_sqm: string;
  source: string;
  requested_system_type: string;
  requested_capacity_kw: string;
  electricity_connection_number: string;
  monthly_bill_amount: string;
  monthly_consumption_kwh: string;
  billing_period_start: string;
  billing_period_end: string;
  notes: string;
}

export interface EnquiryCreated {
  reference: string;
  message: string;
}

/* One row in the sales queue. */
export type EnquiryStatus =
  | "new"
  | "contacting"
  | "qualified"
  | "survey_scheduled"
  | "lost";

export type ContactChannel =
  | "phone"
  | "whatsapp"
  | "email"
  | "site_visit"
  | "other";

export interface StaffMember {
  id: number;
  name: string;
  roles: string[];
  is_administrator: boolean;
}

export interface ContactLogEntry {
  id: number;
  staff_name: string;
  channel: ContactChannel;
  contacted_at: string;
  summary: string;
  reached_customer: boolean;
}

export interface EnquiryListItem {
  revision: number;
  possible_duplicate_of: number | null;
  duplicate_candidate: { id: number; full_name: string; phone: string } | null;
  duplicate_review: string;
  duplicate_review_reason: string;
  id: number;
  reference: string;
  source: string;
  status: EnquiryStatus;
  owner: number | null;
  owner_name: string;
  next_action: string;
  next_action_due: string | null;
  is_overdue: boolean;
  lost_reason: string;
  next_statuses: EnquiryStatus[];
  requested_system_type: SystemType;
  requested_capacity_kw: string | null;
  electricity_connection_number: string;
  monthly_bill_amount: string | null;
  monthly_consumption_kwh: string | null;
  billing_period_start: string | null;
  billing_period_end: string | null;
  has_electricity_bill: boolean;
  notes: string;
  is_possible_duplicate: boolean;
  created_at: string;
  site: {
    id: number;
    address_line: string;
    city: string;
    state: string;
    pincode: string;
    shadow_free_roof_area_sqm: string | null;
    customer: {
      id: number;
      full_name: string;
      phone: string;
      email: string;
      customer_type: CustomerType;
    };
  };
}

/* Django REST Framework wraps list responses in this. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
