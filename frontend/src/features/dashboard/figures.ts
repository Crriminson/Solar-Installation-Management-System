/* One way to show a dashboard figure, on a tile or in its table. */

import { formatMoney, formatQuantity } from "../../lib/format";

export function formatFigure(value: number | string, kind: string) {
  if (kind === "money") return formatMoney(value);
  if (kind === "hours") return formatQuantity(value, "h");
  return String(value);
}
