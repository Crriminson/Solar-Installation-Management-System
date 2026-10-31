/*
  The page shown for a URL that matches nothing.

  It stands on its own, because the catch-all route sits outside both
  shells: someone can land here signed out, from a stale link or a
  typo. So it says what happened, and offers the one way on that always
  works rather than a link that might be refused.
*/

import { Link } from "react-router-dom";

import BrandMark from "./BrandMark";
import { HOME_PATH } from "../navigation";
import styles from "./NotFound.module.css";

export default function NotFound() {
  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <BrandMark />
        <h1 className={styles.title}>This page does not exist</h1>
        <p className={styles.body}>
          The address may have been mistyped, or the record it pointed at may
          have been archived.
        </p>
        <Link className={styles.link} to={HOME_PATH}>
          Go to my work
        </Link>
      </div>
    </main>
  );
}
