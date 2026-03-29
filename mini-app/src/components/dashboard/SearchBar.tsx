interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
}

export function SearchBar({ value, onChange }: SearchBarProps) {
  return (
    <input
      type="text"
      placeholder="Search transactions..."
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-xl px-4 py-3 text-sm mb-3 outline-none"
      style={{
        backgroundColor: "var(--app-card-bg)",
        color: "var(--app-text-primary)",
        border: "1px solid var(--app-border)",
      }}
    />
  );
}
