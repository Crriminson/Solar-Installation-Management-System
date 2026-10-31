/*
  A list's search box.

  The input updates on every keystroke, but the search only runs once
  typing pauses, so each settled term sends one request. Pressing /
  anywhere on the page jumps here.
*/

import { useEffect, useRef, useState } from "react";

import styles from "./SearchInput.module.css";

/* Wait this long after the last keystroke before asking the server. */
const SEARCH_DEBOUNCE_MS = 300;

interface SearchInputProps {
  label: string;
  value: string;
  onSearch: (value: string) => void;
}

export default function SearchInput({ label, value, onSearch }: SearchInputProps) {
  const [typed, setTyped] = useState(value);
  const timer = useRef<number | undefined>(undefined);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      const isTyping = target.closest("input, textarea, select");

      if (event.key === "/" && !isTyping) {
        event.preventDefault();
        input.current?.focus();
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  function handleChange(next: string) {
    setTyped(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => onSearch(next), SEARCH_DEBOUNCE_MS);
  }

  return (
    <input
      ref={input}
      className={styles.search}
      type="search"
      placeholder={label}
      aria-label={label}
      value={typed}
      onChange={(event) => handleChange(event.target.value)}
    />
  );
}
