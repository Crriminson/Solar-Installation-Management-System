/*
  A list's filters, held in the URL.

  Spec.md section 6 asks for this so a refresh or a shared link shows
  the same list. Anything that changes the rows goes back to page one.
*/

import { useSearchParams } from "react-router-dom";

export function useListParams(defaultView = "all") {
  const [params, setParams] = useSearchParams();

  function update(changes: Record<string, string | null>) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [name, value] of Object.entries(changes)) {
          if (value) next.set(name, value);
          else next.delete(name);
        }
        return next;
      },
      { replace: true },
    );
  }

  return {
    search: params.get("search") ?? "",
    view: params.get("view") ?? defaultView,
    page: Number(params.get("page")) || 1,
    selected: params.get("selected"),

    setSearch: (search: string) => update({ search, page: null }),
    setView: (view: string) =>
      update({ view: view === defaultView ? null : view, page: null }),
    setPage: (page: number) => update({ page: page > 1 ? String(page) : null }),
    setSelected: (selected: string | number | null) =>
      update({ selected: selected === null ? null : String(selected) }),
  };
}
