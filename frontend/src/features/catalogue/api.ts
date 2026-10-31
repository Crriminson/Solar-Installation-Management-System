/* Catalogue API calls (F04). */

import { apiGet, apiPatch, apiPost, apiRequest } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type {
  PackageLine,
  PackageTemplate,
  PackageTemplateDetail,
  PackageVersion,
  Product,
  ProductPrice,
  WarrantyPolicy,
} from "./types";

export interface ProductFilters {
  search?: string;
  category?: string;
  repair?: boolean;
  page?: number;
}

export function fetchProducts(filters: ProductFilters) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.category) params.set("category", filters.category);
  if (filters.repair) params.set("repair", "true");
  if (filters.page && filters.page > 1) params.set("page", String(filters.page));

  const query = params.toString();
  return apiGet<Paginated<Product>>(`catalogue/products/${query ? `?${query}` : ""}`);
}

/* Every active product, to fill a picker. */
export function fetchProductChoices() {
  return apiGet<Product[]>("catalogue/products/?picker=true&active=true");
}

export function fetchProduct(productId: string) {
  return apiGet<Product>(`catalogue/products/${productId}/`);
}

export function createProduct(values: Record<string, unknown>) {
  return apiPost<Product>("catalogue/products/", values);
}

export function updateProduct(productId: number | string, values: Record<string, unknown>) {
  return apiPatch<Product>(`catalogue/products/${productId}/`, values);
}

export function addPrice(
  productId: number,
  values: {
    selling_price_excl_tax: string;
    purchase_cost_excl_tax: string | null;
    effective_from: string;
  },
) {
  return apiPost<ProductPrice>(`catalogue/products/${productId}/prices/`, values);
}

export function fetchWarrantyPolicies() {
  return apiGet<WarrantyPolicy[]>("catalogue/warranty-policies/");
}

export function fetchPackages(page: number) {
  const query = page > 1 ? `?page=${page}` : "";
  return apiGet<Paginated<PackageTemplate>>(`catalogue/packages/${query}`);
}

export function fetchPackage(packageId: string) {
  return apiGet<PackageTemplateDetail>(`catalogue/packages/${packageId}/`);
}

export function createPackage(values: {
  kind: string;
  capacity_kw: string | null;
  name: string;
}) {
  return apiPost<PackageTemplate>("catalogue/packages/", values);
}

export function startVersion(packageId: number) {
  return apiPost<PackageVersion>(`catalogue/packages/${packageId}/versions/`);
}

export function updateVersion(versionId: number, values: Record<string, unknown>) {
  return apiPatch<PackageVersion>(`catalogue/versions/${versionId}/`, values);
}

export function activateVersion(versionId: number, revision: number) {
  return apiPost<PackageVersion>(`catalogue/versions/${versionId}/activate/`, { revision });
}

export function addLine(
  versionId: number,
  values: { product: number; basis: string; quantity: string | null; notes: string; revision: number },
) {
  return apiPost<PackageLine>(`catalogue/versions/${versionId}/lines/`, values);
}

export function removeLine(lineId: number, revision: number) {
  return apiRequest<void>(`catalogue/lines/${lineId}/`, { method: "DELETE", body: JSON.stringify({ revision }) });
}
