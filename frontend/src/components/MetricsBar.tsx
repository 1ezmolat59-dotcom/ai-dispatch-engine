import type { BoardSnapshot } from "../api/client";
import { Activity, Users, Clock, Zap } from "lucide-react";

interface Props { board: BoardSnapshot }

export function MetricsBar({ board }: Props) {
  const m = board.metrics;

  const cards = [
    {
      icon: <Activity size={18} className="text-blue-400" />,
      label: "Pending Jobs",
      value: m.total_pending,
      sub: `${m.total_assigned} assigned · ${m.total_in_progress} in progress`,
      accent: m.emergency_jobs > 0 ? "border-red-500/50" : "border-slate-700",
      extra: m.emergency_jobs > 0 ? (
        <span className="text-red-400 text-xs font-bold animate-pulse">
          {m.emergency_jobs} 🚨 EMERGENCY
        </span>
      ) : null,
    },
    {
      icon: <Users size={18} className="text-green-400" />,
      label: "Technicians",
      value: `${m.available_technicians} / ${m.total_technicians}`,
      sub: "available",
      accent: "border-slate-700",
      extra: (
        <span className="text-slate-400 text-xs">
          {m.on_job_technicians} on job · {Math.round(m.utilization_rate * 100)}% utilized
        </span>
      ),
    },
    {
      icon: <Clock size={18} className="text-amber-400" />,
      label: "Avg Wait Time",
      value: `${m.avg_wait_time_minutes.toFixed(0)} min`,
      sub: "for pending jobs",
      accent: m.avg_wait_time_minutes > 30 ? "border-amber-500/50" : "border-slate-700",
      extra: null,
    },
    {
      icon: <Zap size={18} className="text-purple-400" />,
      label: "Utilization",
      value: `${Math.round(m.utilization_rate * 100)}%`,
      sub: "fleet on job",
      accent: "border-slate-700",
      extra: (
        <div className="w-full bg-slate-700 rounded-full h-1.5 mt-1">
          <div
            className="bg-purple-500 h-1.5 rounded-full transition-all duration-700"
            style={{ width: `${m.utilization_rate * 100}%` }}
          />
        </div>
      ),
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map((c) => (
        <div key={c.label} className={`bg-slate-800 rounded-xl p-4 border ${c.accent}`}>
          <div className="flex items-center gap-2 mb-1">
            {c.icon}
            <span className="text-xs text-slate-400 uppercase tracking-wide">{c.label}</span>
          </div>
          <div className="text-2xl font-bold text-white">{c.value}</div>
          <div className="text-xs text-slate-500 mt-0.5">{c.sub}</div>
          {c.extra && <div className="mt-2">{c.extra}</div>}
        </div>
      ))}
    </div>
  );
}
