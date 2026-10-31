/*
  One product, beside the list (F04).

  A price is never edited. A change is a new price from a date, so what
  applied on any past date can always be read back.
*/

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { describeError, fieldErrorsFrom } from "../../api/client";
import Button, { ButtonLink } from "../../components/Button";
import { TextField } from "../../components/Field";
import Reference from "../../components/Reference";
import SidePanel from "../../components/SidePanel";
import { businessToday, formatDate, formatMoney, formatQuantity } from "../../lib/format";
import { useStaffUser } from "../auth/session";
import { addPrice } from "./api";
import { CATEGORY_OPTIONS, labelOf, TRACKING_OPTIONS } from "./labels";
import type { Product } from "./types";
import styles from "./ProductPanel.module.css";

interface Props {
  product: Product;
  onClose: () => void;
}

export default function ProductPanel({ product, onClose }: Props) {
  const user = useStaffUser();

  return (
    <SidePanel label={`Product ${product.sku}`} onClose={onClose}>
      <header className={styles.header}>
        <h2 className={styles.title}>
          <Reference>{product.sku}</Reference>
        </h2>
        <p className={styles.subtitle}>{product.name}</p>
      </header>

      <section className={styles.section}>
        <dl className={styles.facts}>
          <dt>Category</dt>
          <dd>{labelOf(CATEGORY_OPTIONS, product.category)}</dd>
          <dt>Tracking</dt>
          <dd>{labelOf(TRACKING_OPTIONS, product.tracking_method)}</dd>
          <dt>Stocked in</dt>
          <dd>{formatQuantity(product.stocking_quantity, product.unit)}</dd>
          <dt>GST</dt>
          <dd>{Number(product.gst_rate_percent)}%</dd>
          {product.warranty_policy_name && (
            <>
              <dt>Warranty</dt>
              <dd>{product.warranty_policy_name}</dd>
            </>
          )}
          {product.rated_power_w && (
            <>
              <dt>Rated power</dt>
              <dd>{formatQuantity(product.rated_power_w, "W")}</dd>
            </>
          )}
          {product.storage_kwh && (
            <>
              <dt>Storage</dt>
              <dd>{formatQuantity(product.storage_kwh, "kWh")}</dd>
            </>
          )}
          {product.is_repair_part && (
            <>
              <dt>Repair part</dt>
              <dd>Yes</dd>
            </>
          )}
        </dl>

        {user.can_manage_catalogue && (
          <div className={styles.actions}>
            <ButtonLink to={`/catalogue/products/${product.id}/edit`}>Edit product</ButtonLink>
          </div>
        )}
      </section>

      {user.can_manage_catalogue && <NewPriceForm product={product} />}

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Price history</h3>

        {product.prices.length === 0 && <p className={styles.muted}>No price yet.</p>}

        <ul className={styles.history}>
          {product.prices.map((price) => (
            <li key={price.id} className={styles.historyItem}>
              <span>{formatDate(price.effective_from)}</span>
              <span>{formatMoney(price.selling_price_excl_tax)}</span>
              {price.purchase_cost_excl_tax && (
                <span className={styles.muted}>
                  Cost {formatMoney(price.purchase_cost_excl_tax)}
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>
    </SidePanel>
  );
}

function NewPriceForm({ product }: { product: Product }) {
  const queryClient = useQueryClient();
  const [selling, setSelling] = useState("");
  const [cost, setCost] = useState("");
  const [from, setFrom] = useState(businessToday);

  const mutation = useMutation({
    mutationFn: () =>
      addPrice(product.id, {
        selling_price_excl_tax: selling,
        purchase_cost_excl_tax: cost || null,
        effective_from: from,
      }),
    onSuccess: () => {
      setSelling("");
      setCost("");
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });

  const errors = fieldErrorsFrom(mutation.error);

  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>New price</h3>

      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <TextField
          label="Selling price, excluding tax"
          inputMode="decimal"
          unit="₹"
          value={selling}
          onChange={setSelling}
          error={errors.selling_price_excl_tax?.[0]}
        />
        <TextField
          label="Purchase cost, excluding tax"
          inputMode="decimal"
          unit="₹"
          value={cost}
          onChange={setCost}
          error={errors.purchase_cost_excl_tax?.[0]}
        />
        <TextField
          label="Applies from"
          type="date"
          value={from}
          onChange={setFrom}
          error={errors.effective_from?.[0]}
        />

        {mutation.isError && Object.keys(errors).length === 0 && (
          <p className={styles.error} role="alert">
            {describeError(mutation.error)}
          </p>
        )}

        <Button type="submit" disabled={!selling || !from || mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save price"}
        </Button>
      </form>
    </section>
  );
}
