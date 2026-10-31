/* One way to show a dashboard figure, on a tile or in its table. */

import { formatMoney, formatQuantity } from "../../lib/format";

export function formatFigure(value: number | string, kind: string) {
  if (kind === "money") return formatMoney(value);
  if (kind === "hours") return formatQuantity(value, "h");
  return String(value);
}


/*
  The four money figures.

  Spec.md section 6 and F15: quoted margin, operational margin, cash
  collected and cash paid are different metrics and must never read as
  one sum. Giving each its own look is how a glance at the row cannot
  mistake one for another — a shared tile would invite exactly that.

  "basis" says what the number is measured on, which is the part a
  label alone leaves out.
*/

export type FigureIdentity = "projected" | "operational" | "inbound" | "outbound";

interface MoneyFigure {
  identity: FigureIdentity;
  tag: string;
  basis: string;
}

export const MONEY_FIGURES: Record<string, MoneyFigure> = {
  quoted_margin: {
    identity: "projected",
    tag: "Projected",
    basis: "excl. tax",
  },
  operational_margin: {
    identity: "operational",
    tag: "Operational",
    basis: "excl. tax",
  },
  cash_collected: {
    identity: "inbound",
    tag: "Cash in",
    basis: "as recorded",
  },
  cash_paid: {
    identity: "outbound",
    tag: "Cash out",
    basis: "as recorded",
  },
};

/* Written out where the figure is shown, because "margin" on its own
   is the word people read as profit. */
export const OPERATIONAL_MARGIN_FORMULA =
  "Net job revenue excluding taxes and reversals, minus allocated " +
  "equipment cost, minus labour cost, minus direct job expenses. " +
  "A defined business metric, not statutory accounting profit.";
