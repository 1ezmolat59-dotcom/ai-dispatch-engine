import { Star, Briefcase, Wifi, WifiOff } from "lucide-react";
import type { Technician } from "../api/client";
import { StatusBadge } from "./StatusBadge";

const CATEGORY_COLORS: Record<string, string> = {
  hvac:       "bg-blue-600/30  text-blue-300",
  plumbing:   "bg-cyan-600/30  text-cyan-300",
  electrical: "bg-yellow-600/30 text-yellow-300",
  general:    "bg-slate-600/30 text-slate-300",
};

interface Props { tech: Technician; onClick?: () => void }

export function TechnicianCard({ tech, onClick }: Props) {
  const initials = tech.name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
  const hasLocation = tech.location.latitude !== 0 || tech.location.longitude !== 0;

  return (
    <div
      onClick={onClick}
      className="bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl p-4 cursor-pointer transition-colors"
    >
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-sm font-bold text-white shrink-0">
          {initials}
        </div>
        <div className="min-w-0">
          <div className="font-semibold text-white truncate">{tech.name}</div>
          <StatusBadge status={tech.status} />
        </div>
        <div className="ml-auto shrink-0">
          {hasLocation
            ? <Wifi size={14} className="text-green-400" />
            : <WifiOff size={14} className="text-slate-500" />}
        </div>
      </div>

      <div className="flex flex-wrap gap-1 mb-3">
        {tech.skill_categories.map((cat) => (
          <span key={cat} className={`px-1.5 py-0.5 rounded text-xs ${CATEGORY_COLORS[cat] ?? "bg-slate-600 text-slate-300"}`}>
            {cat}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div>
          <div className="text-white font-semibold flex items-center justify-center gap-0.5">
            <Star size={10} className="text-amber-400 fill-amber-400" />
            {tech.customer_rating.toFixed(1)}
          </div>
          <div className="text-slate-500">rating</div>
        </div>
        <div>
          <div className="text-white font-semibold">{Math.round(tech.on_time_rate * 100)}%</div>
          <div className="text-slate-500">on-time</div>
        </div>
        <div>
          <div className="text-white font-semibold flex items-center justify-center gap-0.5">
            <Briefcase size={10} className="text-slate-400" />
            {tech.jobs_completed_today}
          </div>
          <div className="text-slate-500">today</div>
        </div>
      </div>

      {tech.current_job_id && (
        <div className="mt-2 pt-2 border-t border-slate-700 text-xs text-slate-400 truncate">
          On job: <span className="font-mono text-blue-400">{tech.current_job_id.slice(0, 8)}</span>
        </div>
      )}
    </div>
  );
}
