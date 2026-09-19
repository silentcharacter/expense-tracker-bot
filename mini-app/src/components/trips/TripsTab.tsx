/** Trips sub-tab: start a trip, see every trip's totals, open one for its report. */

import { useState } from "react";
import { createTrip } from "../../api/trips";
import type { TripEntry, TripsResponse, UpdateExpenseRequest } from "../../api/types";
import { TripCard } from "./TripCard";
import { TripDetail } from "./TripDetail";
import { TripFormModal } from "./TripFormModal";

interface TripsTabProps {
  trips: TripsResponse | null;
  /** Reload everything after a trip changes (totals feed the other tabs too). */
  refetch: () => Promise<void>;
  onDeleteExpense?: (id: string) => Promise<void>;
  onEditExpense?: (id: string, data: UpdateExpenseRequest) => Promise<void>;
}

export function TripsTab({ trips, refetch, onDeleteExpense, onEditExpense }: TripsTabProps) {
  const [creating, setCreating] = useState(false);
  const [openTrip, setOpenTrip] = useState<TripEntry | null>(null);

  const all = trips?.trips ?? [];
  const active = all.filter((t) => t.is_active);
  const rest = all.filter((t) => !t.is_active);

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={() => setCreating(true)}
        className="w-full py-3 rounded-xl text-sm font-semibold mb-3"
        style={{ background: "var(--app-accent)", color: "#fff", border: "none" }}
      >
        + New trip
      </button>

      {all.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-2xl mb-2">🧳</p>
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--app-text-primary)" }}>
            No trips yet
          </p>
          <p className="text-xs leading-relaxed" style={{ color: "var(--app-text-secondary)" }}>
            Create a trip and every expense you add while it runs is tagged with it —
            categories stay as they are, and you get a separate report per journey.
            <br />
            In the bot: <code>/trip Georgia</code>
          </p>
        </div>
      ) : (
        <>
          {active.map((trip) => (
            <TripCard key={trip.id} trip={trip} onOpen={setOpenTrip} />
          ))}

          {rest.length > 0 && (
            <p
              className="text-xs font-semibold px-1 mt-2 mb-1"
              style={{ color: "var(--app-text-secondary)" }}
            >
              {active.length > 0 ? "Other trips" : "Trips"}
            </p>
          )}
          {rest.map((trip) => (
            <TripCard key={trip.id} trip={trip} onOpen={setOpenTrip} />
          ))}
        </>
      )}

      {creating && (
        <TripFormModal
          onCreate={async (data) => {
            await createTrip(data);
            await refetch();
          }}
          onClose={() => setCreating(false)}
        />
      )}

      {openTrip && (
        <TripDetail
          trip={openTrip}
          onClose={() => setOpenTrip(null)}
          onChanged={refetch}
          onDeleteExpense={onDeleteExpense}
          onEditExpense={onEditExpense}
        />
      )}
    </div>
  );
}
