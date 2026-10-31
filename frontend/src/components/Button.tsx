/*
  The app's button.

  Solar orange is reserved for the one primary action in a view, so
  everything else uses the secondary look. See design.md section 7.
*/

import type { ButtonHTMLAttributes } from "react";
import { Link } from "react-router-dom";

import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export default function Button({
  variant = "secondary",
  type = "button",
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`${styles.button} ${styles[variant]} ${className}`}
      {...props}
    />
  );
}

/* A link that looks like a button, for actions that open another page. */
export function ButtonLink({
  to,
  variant = "secondary",
  children,
}: {
  to: string;
  variant?: Variant;
  children: React.ReactNode;
}) {
  return (
    <Link to={to} className={`${styles.button} ${styles[variant]}`}>
      {children}
    </Link>
  );
}
