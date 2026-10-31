/* Display names for survey values, in the order the forms offer them. */

import type { Option } from "../../components/Field";

export const ROOF_TYPE_OPTIONS: readonly Option[] = [
  { value: "flat_rcc", label: "Flat RCC" },
  { value: "sloped_tile", label: "Sloped tile" },
  { value: "metal_sheet", label: "Metal sheet" },
  { value: "other", label: "Other" },
];

export const ORIENTATION_OPTIONS: readonly Option[] = [
  { value: "S", label: "South" },
  { value: "SE", label: "South-east" },
  { value: "SW", label: "South-west" },
  { value: "E", label: "East" },
  { value: "W", label: "West" },
  { value: "NE", label: "North-east" },
  { value: "NW", label: "North-west" },
  { value: "N", label: "North" },
];

export const SYSTEM_TYPE_OPTIONS: readonly Option[] = [
  { value: "on_grid", label: "On-grid" },
  { value: "off_grid", label: "Off-grid, with battery" },
];

export const GRID_SUITABLE_OPTIONS: readonly Option[] = [
  { value: "true", label: "Suitable" },
  { value: "false", label: "Not suitable" },
];

/* The label for a stored value. */
export function labelFor(options: readonly Option[], value: string) {
  return options.find((option) => option.value === value)?.label ?? value;
}
