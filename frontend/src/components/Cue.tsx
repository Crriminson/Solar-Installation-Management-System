/*
  A live count that opens the records behind it.

  A number you cannot click is not shown. See design.md section 8.
*/

import { Link } from "react-router-dom";

import { ArrowRightIcon, ICON_SIZE, WarningIcon } from "../design/icons";
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
        {showUrgent && <WarningIcon size={ICON_SIZE.inline} aria-hidden />}
        {label}
      </span>
      <ArrowRightIcon className={styles.go} size={ICON_SIZE.inline} aria-hidden />
    </Link>
  );
}
