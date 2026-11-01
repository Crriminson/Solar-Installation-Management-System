/*
  What each role sees in the app's navigation.

  This only decides what is offered. The backend still checks every
  request, so hiding a link is a convenience and never a permission.

  Order matters twice. On a desk it is the order of the sidebar, in
  workflow order rather than alphabetical. On a phone the first few
  visible items become the bottom bar, so the item a role reaches for
  most must come first within its section.
*/

import type { Icon } from "@phosphor-icons/react";

import {
  AssistantIcon,
  DashboardIcon,
  EnquiryIcon,
  FinanceIcon,
  MyWorkIcon,
  OrderIcon,
  PackageTemplateIcon,
  PackingIcon,
  ChatIcon,
  CustomerIcon,
  ProductIcon,
  PurchasingIcon,
  QuotationIcon,
  ScheduleIcon,
  StockIcon,
  SurveyIcon,
  TicketIcon,
  WarrantyIcon,
} from "./design/icons";

export interface NavItem {
  label: string;
  to: string;
  icon: Icon;
  roles: readonly string[];       // empty means everyone
}

export interface NavSection {
  title: string;
  items: readonly NavItem[];
}

/* How many destinations the phone's bottom bar holds before the rest
   move into More. Five is the limit a thumb can hit reliably. */
export const PHONE_BAR_LIMIT = 4;

/* In workflow order, not alphabetical. */
export const NAV_SECTIONS: readonly NavSection[] = [
  {
    title: "",
    items: [
      { label: "My work", to: "/work", icon: MyWorkIcon, roles: [] },
      { label: "Dashboard", to: "/dashboard", icon: DashboardIcon, roles: ["director"] },
    ],
  },
  {
    title: "Sales",
    items: [
      {
        label: "Quotations",
        to: "/quotations",
        icon: QuotationIcon,
        roles: ["sales", "operations_manager", "director"],
      },
      {
        label: "Customers",
        to: "/customers",
        icon: CustomerIcon,
        roles: ["sales", "operations_manager", "support", "finance", "director"],
      },
      {
        label: "Enquiries",
        to: "/enquiries",
        icon: EnquiryIcon,
        roles: ["sales", "operations_manager", "director"],
      },
      {
        label: "Surveys",
        to: "/surveys",
        icon: SurveyIcon,
        roles: ["sales", "operations_manager", "technician", "director"],
      },
    ],
  },
  {
    title: "Delivery",
    items: [
      {
        label: "Orders",
        to: "/orders",
        icon: OrderIcon,
        roles: ["sales", "operations_manager", "finance", "warehouse", "director"],
      },
      {
        label: "Packing",
        to: "/packing",
        icon: PackingIcon,
        roles: ["warehouse", "operations_manager", "sales", "finance", "director"],
      },
      {
        label: "Schedule",
        to: "/schedule",
        icon: ScheduleIcon,
        roles: ["operations_manager", "technician", "support", "sales", "director"],
      },
    ],
  },
  {
    title: "Warehouse",
    items: [
      {
        label: "Stock",
        to: "/stock",
        icon: StockIcon,
        roles: ["warehouse", "operations_manager", "finance", "director"],
      },
      {
        label: "Purchasing",
        to: "/purchasing",
        icon: PurchasingIcon,
        roles: ["warehouse", "operations_manager", "finance", "director"],
      },
    ],
  },
  {
    title: "Support",
    items: [
      {
        label: "Tickets",
        to: "/tickets",
        icon: TicketIcon,
        roles: ["support", "operations_manager", "technician", "finance", "director"],
      },
      {
        label: "Messages",
        to: "/inbox",
        icon: ChatIcon,
        roles: ["support", "operations_manager", "sales"],
      },
      {
        label: "Warranties",
        to: "/warranties",
        icon: WarrantyIcon,
        roles: ["support", "operations_manager", "sales", "warehouse", "finance", "director"],
      },
    ],
  },
  {
    title: "Finance",
    items: [
      {
        label: "Technician pay",
        to: "/technician-pay",
        icon: FinanceIcon,
        roles: ["finance", "operations_manager", "director"],
      },
    ],
  },
  {
    title: "Catalogue",
    items: [
      {
        label: "Products",
        to: "/catalogue/products",
        icon: ProductIcon,
        roles: ["sales", "operations_manager", "warehouse", "finance", "director"],
      },
      {
        label: "Packages",
        to: "/catalogue/packages",
        icon: PackageTemplateIcon,
        roles: ["sales", "operations_manager", "director"],
      },
    ],
  },
  {
    title: "Help",
    items: [
      { label: "Assistant", to: "/assistant", icon: AssistantIcon, roles: [] },
    ],
  },
];

export const HOME_PATH = "/work";

/* Every route that appears in navigation, for the breadcrumb trail. */
export const NAV_ITEMS: readonly NavItem[] = NAV_SECTIONS.flatMap(
  (section) => section.items,
);
