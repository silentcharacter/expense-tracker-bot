import { api } from "./client";
import type {
  AssignTripResponse,
  CreateTripRequest,
  CreateTripResponse,
  DeleteTripResponse,
  SummaryResponse,
  TripEntry,
  TripsResponse,
  UpdateTripRequest,
} from "./types";

export function fetchTrips(): Promise<TripsResponse> {
  return api.get<TripsResponse>("/trips");
}

export function createTrip(data: CreateTripRequest): Promise<CreateTripResponse> {
  return api.post<CreateTripResponse>("/trips", data);
}

export function updateTrip(id: string, data: UpdateTripRequest): Promise<TripEntry> {
  return api.put<TripEntry>(`/trips/${id}`, data);
}

export function deleteTrip(id: string): Promise<DeleteTripResponse> {
  return api.delete<DeleteTripResponse>(`/trips/${id}`);
}

/** Pull existing expenses in the trip's date range into the trip. */
export function assignTripExpenses(
  id: string,
  options: { since?: string; until?: string; overwrite?: boolean } = {},
): Promise<AssignTripResponse> {
  return api.post<AssignTripResponse>(`/trips/${id}/assign`, options);
}

/** Full report for one trip: totals, categories, daily spend over its date range. */
export function fetchTripSummary(id: string): Promise<SummaryResponse> {
  return api.get<SummaryResponse>(`/trips/${id}/summary`);
}
