/*
  The product's mark and name: a sun rising over a panel.

  The mark keeps the solar motif even though the interface palette is
  structural navy — a logo is identity, not a status colour.

  "Solar Ops" is a placeholder until the company's name is known. See
  design.md section 14. Change it here and nowhere else.
*/

import styles from "./BrandMark.module.css";

export const PRODUCT_NAME = "Solar Ops";

const MARK_SIZE = 28;

export default function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={styles.brand}>
      <svg
        width={MARK_SIZE}
        height={MARK_SIZE}
        viewBox="0 0 28 28"
        fill="none"
        role="img"
        aria-label={compact ? PRODUCT_NAME : undefined}
        aria-hidden={compact ? undefined : true}
      >
        <rect width="28" height="28" rx="6" className={styles.tile} />
        <circle cx="14" cy="13" r="5" className={styles.sun} />
        <path
          d="M14 4v2M6.5 7.5 8 9M21.5 7.5 20 9M4 14h2M22 14h2"
          className={styles.rays}
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path d="M5 21.5h18" className={styles.rays} strokeWidth="2.4" strokeLinecap="round" />
      </svg>
      {!compact && <span className={styles.name}>{PRODUCT_NAME}</span>}
    </span>
  );
}
