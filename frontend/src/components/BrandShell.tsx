/*
  The dark side of the public form and the login screen.

  The pattern behind it is a solar array seen from above, so the page
  looks like this company's rather than a form on a blank page.
*/

import type { ReactNode } from "react";

import BrandMark from "./BrandMark";
import styles from "./BrandShell.module.css";

interface BrandShellProps {
  panel: ReactNode;
  children: ReactNode;
}

/* A brand panel beside the page's own content. */
export default function BrandShell({ panel, children }: BrandShellProps) {
  return (
    <div className={styles.shell}>
      <aside className={styles.panel}>
        <BrandMark />
        <div className={styles.panelBody}>{panel}</div>
        <ArrayPattern />
      </aside>
      <main className={styles.content}>{children}</main>
    </div>
  );
}

/* Rows of panels, each divided into cells, fading into the dark. */
function ArrayPattern() {
  return (
    <svg className={styles.array} aria-hidden="true">
      <defs>
        <pattern id="solar-cell" width="36" height="52" patternUnits="userSpaceOnUse">
          <rect x="1" y="1" width="34" height="50" className={styles.cell} />
          <path d="M1 18h34M1 34h34M18 1v50" className={styles.grid} />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#solar-cell)" />
    </svg>
  );
}
