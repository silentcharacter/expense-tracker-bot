import { api } from "./client";
import type { CategoriesResponse, CreateCategoryRequest } from "./types";

export function fetchCategories(): Promise<CategoriesResponse> {
  return api.get<CategoriesResponse>("/categories");
}

export function createCategory(label: string): Promise<CategoriesResponse> {
  const body: CreateCategoryRequest = { label };
  return api.post<CategoriesResponse>("/categories", body);
}
