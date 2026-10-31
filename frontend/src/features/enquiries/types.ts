/* Shapes the enquiry API sends and receives. */

export type CustomerType = "residential" | "commercial";
export type SystemType = "on_grid" | "off_grid" | "undecided";

/* What the public form posts. Optional fields may be left blank. */
export interface EnquiryFormValues {
  full_name: string;
  phone: string;
  email: string;
  customer_type: CustomerType;
  address_line: string;
  city: string;
  state: string;
  pincode: string;
  requested_system_type: SystemType;
  requested_capacity_kw: string;
  monthly_bill_amount: string;
  monthly_consumption_kwh: string;
  notes: string;
}

export interface EnquiryCreated {
  reference: string;
  message: string;
}

/* One row in the sales queue. */
export interface EnquiryListItem {
  id: number;
  reference: string;
  source: string;
  status: string;
  requested_system_type: SystemType;
  requested_capacity_kw: string | null;
  monthly_bill_amount: string | null;
  monthly_consumption_kwh: string | null;
  is_possible_duplicate: boolean;
  created_at: string;
  site: {
    id: number;
    address_line: string;
    city: string;
    state: string;
    pincode: string;
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
