import { useState, useCallback } from "react";
import {
  Cpu, Wifi, WifiOff, RefreshCw, Plus, Users, Briefcase,
  LayoutDashboard, Zap, ChevronRight, AlertCircle, Database
} from "lucide-react";

import { useBoard } from "./hooks/useBoard";
import { api } from "./api/client";
import { MetricsBar } from "./components/MetricsBar";
import { JobCard } from "./components/JobCard";
import { TechnicianCard } from "./components/TechnicianCard";
import { AssignmentFeed } from "./components/AssignmentFeed";
import { AddJobModal } from "./components/AddJobModal";
import { AddTechModal } from "./components/AddTechModal";

type Tab = "board" | "jobs" | "technicians" | "assignments";

export default function App() {
  const { board, status } = useBoard();
  const [tab, setTab] = useState<Tab>("board");
  const [showAddJob, setShowAddJob] = useState(false);
  const [showAddTech, setShowAddTech] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [optimizing, setOptimizing] = useState(false);

  const seedDemo = useCallback(async () => {
    setSeeding(true);
    try { await api.seedDemo(); }
    catch (e) { alert(`Seed failed: ${e}`); }
    finally { setSeeding(false); }
  }, []);

  const triggerOptimize = useCallback(async () => {
    setOptimizing(true);
    try { await api.triggerOptimize(); }
    catch (e) { alert(`Optimize failed: ${e}`); }
    finally { setTimeout(() => setOptimizing(false), 2000); }
  }, []);

  const connected = status === "open";
  const allJobs = board
    ? [...board.pending_jobs, ...board.assigned_jobs, ...board.in_progress_jobs]
    : [];
  const allTechs = board?.technicians ?? [];
  const assignments = board?.recent_assignments ?? [];

  const TABS = [
    { id: "board" as Tab, label: "Board", icon: <LayoutDashboard size={15} />, count: null },
    { id: "jobs" as Tab, label: "Jobs", icon: <Briefcase size={15} />, count: allJobs.length },
    { id: "technicians" as Tab, label: "Technicians", icon: <Users size={15} />, count: allTechs.length },
    { id: "assignments" as Tab, label: "Assignments", icon: <Zap size={15} />, count: assignments.length },
  ];

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="bg-slate-900 border-b border-slate-800 px-4 py-3">
        <div className="max-w-7xl mx-auto flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <Cpu size={16} className="text-white" />
            </div>
            <div>
              <div className="font-bold text-white text-sm">AI Dispatch Engine</div>
              <div className="text-xs text-slate-500">v1.0.0</div>
            </div>
          </div>

          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border ml-2
            ${connected
              ? "bg-green-500/10 border-green-500/30 text-green-400"
              : "bg-red-500/10 border-red-500/30 text-red-400"}`}>
            {connected
              ? <><Wifi size={11} /><span>● LIVE</span></>
              : <><WifiOff size={11} /><span>OFFLINE</span></>}
          </div>

          <div className="ml-auto flex items-center gap-2 flex-wrap">
            <button onClick={seedDemo} disabled={seeding}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-xs text-slate-200 transition-colors disabled:opacity-50">
              <Database size={12} />
              {seeding ? "Seeding..." : "Seed Demo"}
            </button>
            <button onClick={triggerOptimize} disabled={optimizing}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
                ${optimizing ? "bg-purple-700 text-purple-200" : "bg-purple-600 hover:bg-purple-500 text-white"}`}>
              <RefreshCw size={12} className={optimizing ? "animate-spin" : ""} />
              {optimizing ? "Optimizing…" : "Run Optimizer"}
            </button>
            <button onClick={() => setShowAddJob(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-xs text-white font-medium transition-colors">
              <Plus size={12} /> New Job
            </button>
            <button onClick={() => setShowAddTech(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-xs text-slate-200 transition-colors">
              <Plus size={12} /> Add Tech
            </button>
          </div>
        </div>
      </header>

      {/* Nav tabs */}
      <div className="bg-slate-900 border-b border-slate-800 px-4">
        <div className="max-w-7xl mx-auto flex gap-0">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-4 py-3 text-sm border-b-2 transition-colors
                ${tab === t.id
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"}`}>
              {t.icon}
              {t.label}
              {t.count !== null && (
                <span className="ml-1 bg-slate-700 text-slate-300 rounded-full px-1.5 text-xs min-w-[20px] text-center">
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-5">
        {!board && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <AlertCircle size={40} className="text-slate-600 mb-3" />
            <div className="text-slate-400 mb-1">
              {status === "connecting" ? "Connecting to dispatch engine…" : "Cannot connect to backend"}
            </div>
            <div className="text-sm text-slate-600">Make sure the backend is running on port 8000</div>
          </div>
        )}

        {board && (
          <>
            {/* Board tab */}
            {tab === "board" && (
              <div className="space-y-5">
                <MetricsBar board={board} />
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Pending</h3>
                      <span className="bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 px-2 py-0.5 rounded-full text-xs">
                        {board.pending_jobs.length}
                      </span>
                    </div>
                    <div className="space-y-2">
                      {board.pending_jobs.length === 0
                        ? <div className="text-sm text-slate-600 text-center py-6">No pending jobs</div>
                        : board.pending_jobs.map(j => <JobCard key={j.job_id} job={j} compact />)}
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Assigned / En Route</h3>
                      <span className="bg-blue-500/20 text-blue-300 border border-blue-500/30 px-2 py-0.5 rounded-full text-xs">
                        {board.assigned_jobs.length}
                      </span>
                    </div>
                    <div className="space-y-2">
                      {board.assigned_jobs.length === 0
                        ? <div className="text-sm text-slate-600 text-center py-6">No assigned jobs</div>
                        : board.assigned_jobs.map(j => <JobCard key={j.job_id} job={j} compact />)}
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">In Progress</h3>
                        <span className="bg-orange-500/20 text-orange-300 border border-orange-500/30 px-2 py-0.5 rounded-full text-xs">
                          {board.in_progress_jobs.length}
                        </span>
                      </div>
                      <div className="space-y-2">
                        {board.in_progress_jobs.length === 0
                          ? <div className="text-sm text-slate-600 text-center py-4">None active</div>
                          : board.in_progress_jobs.map(j => <JobCard key={j.job_id} job={j} compact />)}
                      </div>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide mb-3">Recent AI Assignments</h3>
                      <AssignmentFeed assignments={board.recent_assignments.slice(0, 5)} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Jobs tab */}
            {tab === "jobs" && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold text-white">All Active Jobs ({allJobs.length})</h2>
                  <button onClick={() => setShowAddJob(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-xs text-white font-medium transition-colors">
                    <Plus size={12} /> New Job
                  </button>
                </div>
                {allJobs.length === 0
                  ? <div className="text-center py-16 text-slate-500">No active jobs. Click "Seed Demo" to load sample data.</div>
                  : <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                      {allJobs.map(j => <JobCard key={j.job_id} job={j} />)}
                    </div>}
              </div>
            )}

            {/* Technicians tab */}
            {tab === "technicians" && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold text-white">Technicians ({allTechs.length})</h2>
                  <button onClick={() => setShowAddTech(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-xs text-white font-medium transition-colors">
                    <Plus size={12} /> Add Technician
                  </button>
                </div>
                {allTechs.length === 0
                  ? <div className="text-center py-16 text-slate-500">No technicians. Click "Seed Demo" to load sample data.</div>
                  : <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                      {allTechs.map(t => <TechnicianCard key={t.tech_id} tech={t} />)}
                    </div>}
              </div>
            )}

            {/* Assignments tab */}
            {tab === "assignments" && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold text-white">AI Assignment Decisions ({assignments.length})</h2>
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span>Last 20 decisions</span>
                    <ChevronRight size={12} />
                  </div>
                </div>
                <div className="max-w-2xl">
                  <AssignmentFeed assignments={assignments} />
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {showAddJob && <AddJobModal onClose={() => setShowAddJob(false)} onCreated={() => {}} />}
      {showAddTech && <AddTechModal onClose={() => setShowAddTech(false)} onCreated={() => {}} />}
    </div>
  );
}
