import { CheckCircle, Navigation, Clock } from "lucide-react";
import type { AssignmentResult } from "../api/client";

interface Props { assignments: AssignmentResult[] }

export function AssignmentFeed({ assignments }: Props) {
  if (!assignments.length) {
    return (
      <div className="text-center text-slate-500 text-sm py-8">
        No assignments yet — waiting for optimizer...
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {assignments.map((a) => (
        <div key={`${a.job_id}-${a.assigned_at}`}
          className="bg-slate-800/60 border border-slate-700 rounded-lg p-3">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <CheckCircle size={14} className="text-green-400 shrink-0" />
              <span className="text-sm font-medium text-white">{a.tech_name}</span>
            </div>
            <span className="text-xs text-slate-500 font-mono">
              {new Date(a.assigned_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
          <div className="text-xs text-slate-400 ml-5">
            Job <span className="font-mono text-blue-400">{a.job_id.slice(0, 8)}</span>
          </div>
          <div className="flex items-center gap-4 mt-2 ml-5 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <Navigation size={10} />
              {a.distance_km.toFixed(1)} km · {Math.round(a.travel_time_minutes)} min
            </span>
            <span className="flex items-center gap-1">
              <Clock size={10} />
              {a.predicted_job_duration_minutes}m job
            </span>
            {a.scores && (
              <span className="text-purple-400 font-medium">
                Score {(a.scores.total * 100).toFixed(0)}
              </span>
            )}
          </div>
          {a.scores && (
            <div className="mt-2 ml-5 flex gap-1 flex-wrap">
              {[
                ["dist", a.scores.distance],
                ["skill", a.scores.skill_match],
                ["load", a.scores.workload],
                ["perf", a.scores.performance],
                ["avail", a.scores.availability],
              ].map(([label, val]) => (
                <div key={label as string} className="flex items-center gap-1">
                  <div className="h-1 rounded-full bg-slate-600 w-12 overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full"
                      style={{ width: `${(val as number) * 100}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-slate-500">{label as string}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
