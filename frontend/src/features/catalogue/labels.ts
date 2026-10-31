/* Display names for catalogue values, in the order forms offer them. */

import type { Option } from "../../components/Field";

export const CATEGORY_OPTIONS: readonly Option[] = [
  { value: "panel", label: "Solar panel" },
  { value: "inverter", label: "Inverter" },
  { value: "battery", label: "Battery" },
  { value: "charge_controller", label: "Charge controller" },
  { value: "mounting", label: "Mounting structure" },
  { value: "cable", label: "Cable" },
  { value: "connector", label: "Connector" },
  { value: "protection", label: "Switch or protection device" },
  { value: "earthing", label: "Earthing material" },
  { value: "service", label: "Labour or service" },
  { value: "other", label: "Other" },
];

export const TRACKING_OPTIONS: readonly Option[] = [
  { value: "serialized", label: "Serialized" },
  { value: "bulk", label: "Bulk, by batch" },
  { value: "service", label: "Service, no stock" },
];

export const PACKAGE_KIND_OPTIONS: readonly Option[] = [
  { value: "on_grid", label: "On-Grid" },
  { value: "off_grid", label: "Off-Grid" },
  { value: "panel_set", label: "Solar Panel Set" },
  { value: "installation", label: "Installation service" },
];

export const BASIS_OPTIONS: readonly Option[] = [
  { value: "fixed", label: "Fixed quantity" },
  { value: "cable_route", label: "From the surveyed cable route" },
  { value: "battery_load", label: "From the off-grid load and backup" },
];

export const YES_NO_OPTIONS: readonly Option[] = [
  { value: "false", label: "No" },
  { value: "true", label: "Yes" },
];

/* Kinds sold at a stated size. */
export const SIZED_KINDS = ["on_grid", "off_grid"];

export function labelOf(options: readonly Option[], value: string) {
  return options.find((option) => option.value === value)?.label ?? value;
}
