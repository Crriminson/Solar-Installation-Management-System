/* The customer as a whole (F01). */

export interface CustomerRow {
  id: number;
  full_name: string;
  phone: string;
  email: string;
  customer_type: string;
  city: string;
  site_count: number;
  enquiry_count: number;
  order_count: number;
  created_at: string;
}

export interface CustomerSite {
  id: number;
  address_line: string;
  city: string;
  state: string;
  pincode: string;
}

export interface CustomerEnquiry {
  id: number;
  reference: string;
  status: string;
  owner_name: string;
  created_at: string;
}

export interface CustomerOrder {
  id: number;
  reference: string;
  status: string;
  gross: string;
  outstanding: string;
  created_at: string;
}

export interface CustomerUnit {
  id: number;
  asset_id: string;
  serial_number: string;
  product: string;
  warranty_status: string;
  covered_until: string | null;
}

export interface CustomerTicket {
  id: number;
  reference: string;
  status: string;
  priority: string;
  fault: string;
  complaint_at: string;
}

export interface CustomerRecord {
  id: number;
  full_name: string;
  phone: string;
  email: string;
  customer_type: string;
  created_at: string;
  sites: CustomerSite[];
  enquiries: CustomerEnquiry[];
  orders: CustomerOrder[];
  equipment: CustomerUnit[];
  tickets: CustomerTicket[];
  telegram: { linked: boolean; chat_name: string };
}
