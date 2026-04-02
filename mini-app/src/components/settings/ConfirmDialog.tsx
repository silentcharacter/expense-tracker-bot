/** Modal confirmation dialog for destructive actions. */

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center pb-8 px-4"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div
        className="w-full max-w-sm rounded-2xl overflow-hidden"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="px-5 pt-5 pb-4 text-center">
          <p className="text-base font-semibold mb-1.5" style={{ color: "var(--app-text-primary)" }}>
            {title}
          </p>
          <p className="text-sm leading-relaxed" style={{ color: "var(--app-text-secondary)" }}>
            {message}
          </p>
        </div>

        <div
          className="border-t"
          style={{ borderColor: "var(--app-border)" }}
        />

        <button
          className="w-full py-3.5 text-sm font-semibold"
          style={{ color: danger ? "var(--app-danger)" : "var(--app-accent)" }}
          onClick={onConfirm}
          disabled={loading}
        >
          {loading ? "Please wait…" : confirmLabel}
        </button>

        <div className="border-t" style={{ borderColor: "var(--app-border)" }} />

        <button
          className="w-full py-3.5 text-sm"
          style={{ color: "var(--app-text-primary)" }}
          onClick={onCancel}
          disabled={loading}
        >
          {cancelLabel}
        </button>
      </div>
    </div>
  );
}
