/*
  Product catalogue (F04).

  Prices shown exclude tax, and say so. Purchase cost appears only for
  people allowed to see it: the API leaves it out for everyone else, so
  hiding the column here is not what protects it.
*/

import { useMemo } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { ButtonLink } from "../../components/Button";
import DataTable, { type Column } from "../../components/DataTable";
import FilterTabs from "../../components/FilterTabs";
import PageHeader from "../../components/PageHeader";
import Pagination from "../../components/Pagination";
import Reference from "../../components/Reference";
import SearchInput from "../../components/SearchInput";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { useListParams } from "../../components/useListParams";
import { formatMoney } from "../../lib/format";
import { useStaffUser } from "../auth/session";
import { fetchProducts } from "./api";
import { CATEGORY_OPTIONS, labelOf } from "./labels";
import ProductPanel from "./ProductPanel";
import type { Product } from "./types";
import styles from "./ProductList.module.css";

const VIEWS = [
  { key: "all", label: "All" },
  { key: "panel", label: "Panels" },
  { key: "inverter", label: "Inverters" },
  { key: "battery", label: "Batteries" },
  { key: "cable", label: "Cable" },
  { key: "service", label: "Labour" },
  { key: "repair", label: "Repair parts" },
];

export default function ProductList() {
  const user = useStaffUser();
  const list = useListParams();

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["products", list.search, list.view, list.page],
    queryFn: () =>
      fetchProducts({
        search: list.search,
        category: list.view === "all" || list.view === "repair" ? undefined : list.view,
        repair: list.view === "repair",
        page: list.page,
      }),
    placeholderData: keepPreviousData,
  });

  const columns = useMemo(() => buildColumns(user.can_view_costs), [user.can_view_costs]);
  const selected =
    data?.results.find((product) => String(product.id) === list.selected) ?? null;

  return (
    <>
      <PageHeader
        title="Products"
        actions={
          user.can_manage_catalogue && (
            <ButtonLink to="/catalogue/products/new" variant="primary">
              New product
            </ButtonLink>
          )
        }
      />

      <FilterTabs
        label="Filter products"
        options={VIEWS}
        value={list.view}
        onChange={list.setView}
      />

      <div className={styles.toolbar}>
        <SearchInput
          label="Search SKU or name"
          value={list.search}
          onSearch={list.setSearch}
        />
        {data && (
          <span className={styles.muted}>
            {data.count} {data.count === 1 ? "product" : "products"} · Prices exclude tax
          </span>
        )}
      </div>

      {isPending && <LoadingMessage label="Loading products…" />}
      {isError && <ErrorMessage error={error} onRetry={refetch} />}

      {data && data.results.length === 0 && (
        <EmptyMessage>
          {list.search ? `No product matches "${list.search}".` : "No products here yet."}
        </EmptyMessage>
      )}

      {data && data.results.length > 0 && (
        <>
          <DataTable
            caption="Products"
            columns={columns}
            rows={data.results}
            rowKey={(product) => product.id}
            selectedKey={selected?.id}
            onRowClick={(product) => list.setSelected(product.id)}
          />
          <Pagination page={list.page} count={data.count} onChange={list.setPage} />
        </>
      )}

      {selected && (
        <ProductPanel
          key={selected.id}
          product={selected}
          onClose={() => list.setSelected(null)}
        />
      )}
    </>
  );
}


// ============================================================
// Helpers
// ============================================================

function buildColumns(showCosts: boolean): readonly Column<Product>[] {
  const columns: Column<Product>[] = [
    { header: "SKU", render: (product) => <Reference>{product.sku}</Reference> },
    {
      header: "Product",
      render: (product) => (
        <>
          {product.name}
          {!product.is_active && <div className={styles.muted}>Retired</div>}
        </>
      ),
    },
    { header: "Category", render: (product) => labelOf(CATEGORY_OPTIONS, product.category) },
    { header: "Unit", render: (product) => product.unit },
    {
      header: "Selling price",
      numeric: true,
      render: (product) =>
        product.current_price ? (
          formatMoney(product.current_price.selling_price_excl_tax)
        ) : (
          <span className={styles.missing}>No price</span>
        ),
    },
  ];

  if (showCosts) {
    columns.push({
      header: "Cost",
      numeric: true,
      render: (product) => {
        const cost = product.current_price?.purchase_cost_excl_tax;
        return cost ? formatMoney(cost) : "–";
      },
    });
  }

  return columns;
}
