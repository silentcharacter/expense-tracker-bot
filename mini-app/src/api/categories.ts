import { api } from "./client";
import type { CategoriesResponse, CreateCategoryRequest } from "./types";

export function fetchCategories(): Promise<CategoriesResponse> {
  return api.get<CategoriesResponse>("/categories");
}

export function createCategory(label: string): Promise<CategoriesResponse> {
  const body: CreateCategoryRequest = { label };
  return api.post<CategoriesResponse>("/categories", body);
}

export function createSubcategory(catSlug: string, label: string): Promise<CategoriesResponse> {
  return api.post<CategoriesResponse>(`/categories/${catSlug}/subcategories`, { label });
}

export function deleteCategory(catSlug: string): Promise<CategoriesResponse> {
  return api.delete<CategoriesResponse>(`/categories/${catSlug}`);
}

export function deleteSubcategory(catSlug: string, subSlug: string): Promise<CategoriesResponse> {
  return api.delete<CategoriesResponse>(`/categories/${catSlug}/subcategories/${subSlug}`);
}
