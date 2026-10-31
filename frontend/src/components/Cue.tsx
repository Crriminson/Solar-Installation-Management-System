/*
  A live count that opens the records behind it.

  A number you cannot click is not shown. See design.md section 4.
*/

import { Link } from "react-router-dom";

import styles from "./Cue.module.css";

interface CueProps {
  label: string;
  count: number | undefined;
  to: string;
  urgent?: boolean;
}

export default function Cue({ label, count, to, urgent = false }: CueProps) {
  const showUrgent = urgent && Boolean(count);

  return (
    <Link className={`${styles.cue} ${showUrgent ? styles.urgent : ""}`} to={to}>
      <span className={styles.count}>{count ?? "–"}</span>
      <span className={styles.label}>
        {showUrgent && <span aria-hidden="true">▲ </span>}
        {label}
      </span>
    </Link>
  );
}
