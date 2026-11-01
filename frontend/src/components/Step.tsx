/*
  One step in a record, open only when it is the one to do.

  A record screen can carry five forms at once. Showing them all asks
  the person to work out which one they need; showing the next one open
  and the rest folded away answers that for them. Nothing is hidden -
  every step is still there, and a folded one opens on a click.

  `done` marks a step that has already been satisfied, so the folded
  row still says so without being opened.
*/

import { useState, type ReactNode } from "react";

import { CaretDownIcon, ConfirmIcon, ICON_SIZE } from "../design/icons";
import styles from "./Step.module.css";

interface StepProps {
  title: string;
  summary?: ReactNode;
  done?: boolean;
  openByDefault?: boolean;
  children: ReactNode;
}

export default function Step({
  title,
  summary,
  done = false,
  openByDefault = false,
  children,
}: StepProps) {
  const [open, setOpen] = useState(openByDefault);

  return (
    <section className={`${styles.step} ${open ? styles.stepOpen : ""}`}>
      <button
        type="button"
        className={styles.head}
        aria-expanded={open}
        onClick={() => setOpen((on) => !on)}
      >
        <span className={styles.mark} aria-hidden="true">
          {done && <ConfirmIcon size={ICON_SIZE.inline} />}
        </span>

        <span className={styles.titles}>
          <span className={styles.title}>{title}</span>
          {summary && !open && <span className={styles.summary}>{summary}</span>}
        </span>

        <CaretDownIcon
          className={open ? styles.caretOpen : styles.caret}
          size={ICON_SIZE.control}
          aria-hidden
        />
      </button>

      {open && <div className={styles.body}>{children}</div>}
    </section>
  );
}
