/*
  The dashboard's filters, shared with its drill-downs through the URL.

  A drill-down keeps the filters it was opened with, so the rows on
  screen are always the rows behind the number that was clicked.
*/

export const PERIODS = [
  { key: "today", label: "Today" },
  { key: "week", label: "This week" },
  { key: "month", label: "This month" },
  { key: "custom", label: "Custom range" },
];

export const PROJECT_STATUSES = [
  { value: "", label: "Every project status" },
  { value: "confirmed", label: "Confirmed" },
  { value: "delivered", label: "Delivered" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

export const SYSTEM_TYPES = [
  { value: "", label: "Every system type" },
  { value: "on_grid", label: "On-Grid" },
  { value: "off_grid", label: "Off-Grid" },
  { value: "undecided", label: "Not decided" },
];

const FILTER_NAMES = ["period", "from", "to", "status", "system_type"];

/* Only what the API reads, so stray parameters never reach it. */
export function dashboardQuery(params: URLSearchParams) {
  const query = new URLSearchParams();
  for (const name of FILTER_NAMES) {
    const value = params.get(name);
    if (value) query.set(name, value);
  }
  return query;
}
