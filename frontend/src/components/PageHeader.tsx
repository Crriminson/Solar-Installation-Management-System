/*
  The top of every staff page: where you are, what this is, and the one
  primary action. Other actions go beside it, never above it.
*/

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import styles from "./PageHeader.module.css";

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  back?: { to: string; label: string };
  actions?: ReactNode;
  children?: ReactNode;
}

export default function PageHeader({
  title,
  subtitle,
  back,
  actions,
  children,
}: PageHeaderProps) {
  return (
    <header className={styles.header}>
      {back && (
        <Link className={styles.back} to={back.to}>
          ‹ {back.label}
        </Link>
      )}

      <div className={styles.top}>
        <div className={styles.titles}>
          <h1 className={styles.title}>{title}</h1>
          {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>

      {children}
    </header>
  );
}
