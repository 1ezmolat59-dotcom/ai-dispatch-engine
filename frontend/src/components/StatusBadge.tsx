const STATUS_STYLES: Record<string, string> = {
  // Job statuses
  pending:     "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30",
  assigned:    "bg-blue-500/20   text-blue-300   border border-blue-500/30",
  en_route:    "bg-purple-500/20 text-purple-300 border border-purple-500/30",
  in_progress: "bg-orange-500/20 text-orange-300 border border-orange-500/30",
  completed:   "bg-green-500/20  text-green-300  border border-green-500/30",
  cancelled:   "bg-slate-500/20  text-slate-400  border border-slate-500/30",
  on_hold:     "bg-rose-500/20   text-rose-300   border border-rose-500/30",
  // Tech statuses
  available:   "bg-green-500/20  text-green-300  border border-green-500/30",
  on_job:      "bg-orange-500/20 text-orange-300 border border-orange-500/30",
  on_break:    "bg-slate-500/20  text-slate-400  border border-slate-500/30",
  off_duty:    "bg-slate-600/20  text-slate-500  border border-slate-600/30",
  unavailable: "bg-red-500/20    text-red-300    border border-red-500/30",
};

const PRIORITY_STYLES: Record<number, string> = {
  1: "bg-red-600    text-white",
  2: "bg-orange-500 text-white",
  3: "bg-amber-500  text-white",
  4: "bg-slate-600  text-slate-200",
  5: "bg-slate-700  text-slate-400",
};

const PRIORITY_LABELS: Record<number, string> = {
  1: "🚨 EMERGENCY", 2: "⚡ URGENT", 3: "▲ HIGH", 4: "NORMAL", 5: "LOW",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium uppercase tracking-wide ${STATUS_STYLES[status] ?? "bg-slate-600 text-slate-300"}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: number }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold ${PRIORITY_STYLES[priority] ?? "bg-slate-600 text-white"}`}>
      {PRIORITY_LABELS[priority] ?? `P${priority}`}
    </span>
  );
}
