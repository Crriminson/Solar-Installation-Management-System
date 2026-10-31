/*
  The frame for a screen the customer is handed the device on.

  Spec.md F06: the customer sees their document "and nothing else — no
  margins, no other customers, no staff navigation". So this shell has
  no navigation at all, and no way back into the app. What it does keep
  is the product mark, so the person signing can see whose document
  they are looking at, and a measure that stays readable on a tablet.

  Staff get back by using the device's own back gesture, which is how
  they handed it over in the first place.
*/

import type { ReactNode } from "react";

import BrandMark from "./BrandMark";
import styles from "./PresentShell.module.css";

export default function PresentShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <header className={styles.bar}>
        <BrandMark />
      </header>
      <main className={styles.content}>{children}</main>
    </div>
  );
}
