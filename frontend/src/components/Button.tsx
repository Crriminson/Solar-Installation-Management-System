/*
  The app's button.

  Blue is reserved for the one primary action in a view, so everything
  else uses the secondary or quiet look. See design.md section 3.

  A button that starts a request takes `loading`: it stays the same
  width, swaps its icon for a spinner and stops accepting clicks, so a
  slow action never looks like a dead one.
*/

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

import { SpinnerIcon } from "../design/icons";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "quiet" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: ReactNode;
  loading?: boolean;
}

export default function Button({
  variant = "secondary",
  type = "button",
  className = "",
  icon,
  loading = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`${styles.button} ${styles[variant]} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <SpinnerIcon className={styles.spinner} aria-hidden /> : icon}
      {children}
    </button>
  );
}

/* A link that looks like a button, for actions that open another page. */
export function ButtonLink({
  to,
  variant = "secondary",
  reloadDocument = false,
  icon,
  children,
}: {
  to: string;
  variant?: Variant;
  reloadDocument?: boolean;     // a real page load, for a file download
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Link
      to={to}
      reloadDocument={reloadDocument}
      className={`${styles.button} ${styles[variant]}`}
    >
      {icon}
      {children}
    </Link>
  );
}

/* A button whose icon is its whole content. The label is still
   required, and becomes the accessible name and the tooltip. */
export function IconButton({
  label,
  icon,
  variant = "quiet",
  type = "button",
  className = "",
  ...props
}: Omit<ButtonProps, "children" | "icon"> & { label: string; icon: ReactNode }) {
  return (
    <button
      type={type}
      className={`${styles.button} ${styles[variant]} ${styles.iconOnly} ${className}`}
      aria-label={label}
      title={label}
      {...props}
    >
      {icon}
    </button>
  );
}
