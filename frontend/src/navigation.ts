/*
  What each role sees in the app's navigation.

  This only decides what is offered. The backend still checks every
  request, so hiding a link is a convenience and never a permission.
*/

export interface NavItem {
  label: string;
  to: string;
  roles: readonly string[];       // empty means everyone
}

export interface NavSection {
  title: string;
  items: readonly NavItem[];
}

/* In workflow order, not alphabetical. */
export const NAV_SECTIONS: readonly NavSection[] = [
  {
    title: "",
    items: [{ label: "My work", to: "/work", roles: [] }],
  },
  {
    title: "Sales",
    items: [
      {
        label: "Enquiries",
        to: "/enquiries",
        roles: ["sales", "operations_manager", "director"],
      },
      {
        label: "Surveys",
        to: "/surveys",
        roles: ["sales", "operations_manager", "technician", "director"],
      },
    ],
  },
  {
    title: "Catalogue",
    items: [
      {
        label: "Products",
        to: "/catalogue/products",
        roles: ["sales", "operations_manager", "warehouse", "finance", "director"],
      },
      {
        label: "Packages",
        to: "/catalogue/packages",
        roles: ["sales", "operations_manager", "director"],
      },
    ],
  },
];

export const HOME_PATH = "/work";
