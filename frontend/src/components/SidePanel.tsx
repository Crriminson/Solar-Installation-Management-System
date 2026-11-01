/*
  A floating window over the work area, for quick work without leaving
  the list behind it.

  It is centred in the content column rather than the viewport, so the
  navigation stays visible and the person can still see where they are.
  Escape closes it, clicking away closes it, and focus returns to the
  row that opened it so someone working by keyboard keeps their place.
*/

import { useEffect, useRef, type ReactNode } from "react";

import { CloseIcon, ICON_SIZE } from "../design/icons";
import styles from "./SidePanel.module.css";

interface SidePanelProps {
  label: string;
  onClose: () => void;
  children: ReactNode;
}

export default function SidePanel({ label, onClose, children }: SidePanelProps) {
  const panel = useRef<HTMLElement>(null);

  // Kept in a ref so a new function on each render does not rerun the
  // effect below, which would pull focus back into the panel.
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panel.current?.focus();

    function handleKey(event: KeyboardEvent) {
      // A confirmation dialog handles its own Escape.
      if (event.key === "Escape" && !document.querySelector("dialog[open]")) {
        close.current();
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("keydown", handleKey);
      opener?.focus();
    };
  }, []);

  return (
    <div
      className={styles.scrim}
      /* Clicking the dimmed area closes, but a click that started
         inside the window and ended outside it must not. */
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        ref={panel}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
      >
        <button
          type="button"
          className={styles.close}
          aria-label="Close"
          onClick={onClose}
        >
          <CloseIcon size={ICON_SIZE.section} aria-hidden />
        </button>
        {children}
      </aside>
    </div>
  );
}
