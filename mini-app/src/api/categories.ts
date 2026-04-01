import { api } from "./client";
import type { CategoriesResponse } from "./types";

export function fetchCategories(): Promise<CategoriesResponse> {
  return api.get<CategoriesResponse>("/categories");
}
