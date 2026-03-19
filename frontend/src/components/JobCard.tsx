import { MapPin, Clock, Wrench, ExternalLink } from "lucide-react";
import type { Job } from "../api/client";
import { StatusBadge, PriorityBadge } from "./StatusBadge";

const JOB_TYPE_LABELS: Record<string, string> = {
  hvac_repair: "HVAC Repair", hvac_install: "HVAC Install",
  hvac_maintenance: "HVAC Maintenance", hvac_emergency: "HVAC Emergency",
  hvac_diagnostic: "HVAC Diagnostic", plumbing_repair: "Plumbing Repair",
  plumbing_install: "Plumbing Install", plumbing_emergency: "Plumbing Emergency",
  drain_cleaning: "Drain Cleaning", water_heater: "Water Heater",
  electrical_repair: "Electrical Repair", electrical_install: "Electrical Install",
  electrical_inspection: "Electrical Inspection", panel_upgrade: "Panel Upgrade",
  ev_charger: "EV Charger", maintenance: "Maintenance",
  inspection: "Inspection", estimate: "Estimate",
};

interface Props {
  job: Job;
  onClick?: () => void;
  compact?: boolean;
}

export function JobCard({ job, onClick, compact }: Props) {
  const eta = job.predicted_eta ? new Date(job.predicted_eta) : null;
  const created = new Date(job.created_at);
  const waitMin = Math.floor((Date.now() - created.getTime()) / 60000);

  return (
    <div
      onClick={onClick}
      className={`bg-slate-800 border rounded-xl p-4 cursor-pointer hover:bg-slate-750 transition-colors
        ${job.priority === 1 ? "border-red-500/60 shadow-red-500/10 shadow-lg" : "border-slate-700 hover:border-slate-600"}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex flex-wrap gap-1.5">
          <PriorityBadge priority={job.priority} />
          <StatusBadge status={job.status} />
        </div>
        <span className="text-xs text-slate-500 shrink-0 font-mono">
          {job.fsm_job_id ?? job.job_id.slice(0, 8)}
        </span>
      </div>

      <div className="flex items-center gap-1.5 mb-1">
        <Wrench size={13} className="text-slate-400 shrink-0" />
        <span className="text-sm font-semibold text-white">
          {JOB_TYPE_LABELS[job.job_type] ?? job.job_type}
        </span>
      </div>

      <div className="flex items-center gap-1.5 mb-1">
        <MapPin size={13} className="text-slate-400 shrink-0" />
        <span className="text-xs text-slate-300 truncate">{job.customer.name}</span>
        {!compact && (
          <span className="text-xs text-slate-500 truncate">· {job.customer.address}</span>
        )}
      </div>

      {!compact && job.description && (
        <p className="text-xs text-slate-500 mt-1 line-clamp-2">{job.description}</p>
      )}

      <div className="flex items-center justify-between mt-3 pt-2 border-t border-slate-700">
        <div className="flex items-center gap-1 text-xs text-slate-400">
          <Clock size={11} />
          <span>Waiting {waitMin}m</span>
        </div>
        {eta && (
          <span className="text-xs text-blue-400 font-medium">
            ETA {eta.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
        {job.predicted_duration_minutes && (
          <span className="text-xs text-slate-500">~{job.predicted_duration_minutes}m job</span>
        )}
      </div>

      {job.assignment?.maps_deep_link_google && (
        <a
          href={job.assignment.maps_deep_link_google}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="mt-2 flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
        >
          <ExternalLink size={11} /> Navigate
        </a>
      )}
    </div>
  );
}
