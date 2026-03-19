const API_KEY = import.meta.env.VITE_API_KEY ?? "dev-secret-key";
// On web: use relative path (proxied by Vite dev server → localhost:8000)
// On device: set VITE_API_BASE_URL to your deployed server, e.g. https://api.yourdomain.com
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "") + "/api/v1";

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      ...(opts.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${body}`);
  }
  return res.json();
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

export const api = {
  // Jobs
  listJobs: (status?: string) =>
    request<Job[]>(`/jobs${status ? `?status=${status}` : ""}`),
  createJob: (body: CreateJobPayload) =>
    request<{ job_id: string }>("/jobs", { method: "POST", body: JSON.stringify(body) }),
  completeJob: (jobId: string, body: { actual_duration_minutes: number; notes?: string }) =>
    request<unknown>(`/jobs/${jobId}/complete`, { method: "PATCH", body: JSON.stringify(body) }),
  cancelJob: (jobId: string) =>
    request<unknown>(`/jobs/${jobId}`, { method: "DELETE" }),
  manualAssign: (jobId: string, techId: string) =>
    request<AssignmentResult>(`/jobs/${jobId}/assign`, {
      method: "POST",
      body: JSON.stringify({ tech_id: techId }),
    }),

  // Technicians
  listTechs: () => request<Technician[]>("/technicians"),
  createTech: (body: CreateTechPayload) =>
    request<{ tech_id: string; name: string }>("/technicians", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateLocation: (techId: string, lat: number, lon: number) =>
    request<unknown>(`/technicians/${techId}/location`, {
      method: "PATCH",
      body: JSON.stringify({ latitude: lat, longitude: lon }),
    }),
  updateStatus: (techId: string, status: string) =>
    request<unknown>(`/technicians/${techId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),

  // Dispatch board
  getBoard: () => request<BoardSnapshot>("/dispatch/board"),
  getMetrics: () => request<Metrics>("/dispatch/metrics"),
  getAssignments: (limit = 20) =>
    request<AssignmentResult[]>(`/dispatch/assignments?limit=${limit}`),
  triggerOptimize: () =>
    request<unknown>("/dispatch/optimize", { method: "POST" }),

  // Demo
  seedDemo: () =>
    request<{ seeded: boolean; technicians_added: number; jobs_added: number }>(
      "/demo/seed",
      { method: "POST" }
    ),
  resetDemo: () => request<unknown>("/demo/reset", { method: "DELETE" }),
};

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CustomerInfo {
  customer_id: string;
  name: string;
  phone: string;
  email: string;
  address: string;
  latitude: number;
  longitude: number;
}

export interface Job {
  job_id: string;
  job_type: string;
  priority: number;
  status: string;
  customer: CustomerInfo;
  assigned_tech_id: string | null;
  predicted_duration_minutes: number | null;
  predicted_eta: string | null;
  scheduled_start: string | null;
  created_at: string;
  description: string;
  dispatch_score: number;
  fsm_job_id: string | null;
  assignment?: AssignmentResult;
}

export interface Technician {
  tech_id: string;
  name: string;
  phone: string;
  email: string;
  status: string;
  skills: { skill_id: string; name: string; category: string; level: number }[];
  skill_categories: string[];
  current_job_id: string | null;
  job_queue_length: number;
  location: { latitude: number; longitude: number };
  jobs_completed_today: number;
  customer_rating: number;
  on_time_rate: number;
  years_experience: number;
  fsm_tech_id: string | null;
}

export interface AssignmentScore {
  total: number;
  distance: number;
  skill_match: number;
  workload: number;
  performance: number;
  availability: number;
}

export interface AssignmentResult {
  job_id: string;
  tech_id: string;
  tech_name: string;
  assigned_at: string;
  travel_time_minutes: number;
  predicted_job_duration_minutes: number;
  predicted_arrival: string | null;
  predicted_completion: string | null;
  distance_km: number;
  maps_deep_link_google: string | null;
  maps_deep_link_apple: string | null;
  scores: AssignmentScore | null;
  alternatives: { tech_id: string; tech_name: string; score: number; distance_km: number }[];
  customer_eta_sent: boolean;
  eta_message: string;
  duration_confidence: number;
}

export interface BoardSnapshot {
  snapshot_id: string;
  timestamp: string;
  pending_jobs: Job[];
  assigned_jobs: Job[];
  in_progress_jobs: Job[];
  completed_jobs_today: Job[];
  technicians: Technician[];
  recent_assignments: AssignmentResult[];
  metrics: {
    total_pending: number;
    total_assigned: number;
    total_in_progress: number;
    emergency_jobs: number;
    total_technicians: number;
    available_technicians: number;
    on_job_technicians: number;
    utilization_rate: number;
    avg_wait_time_minutes: number;
  };
}

export interface Metrics {
  jobs: {
    pending: number;
    assigned: number;
    in_progress: number;
    emergencies_active: number;
    avg_wait_time_minutes: number;
  };
  technicians: {
    total: number;
    available: number;
    on_job: number;
    utilization_rate: number;
  };
  ai: {
    optimizer_assignments: number;
    avg_assignment_score: number;
    ml_predictor_trained: boolean;
    ml_training_samples: number;
  };
  engine: { running: boolean; optimization_interval_seconds: number };
}

export interface CreateJobPayload {
  job_type: string;
  priority: number;
  description?: string;
  customer: {
    customer_id: string;
    name: string;
    phone: string;
    email: string;
    address: string;
    latitude: number;
    longitude: number;
  };
  equipment?: { make?: string; model?: string; year_installed?: number };
}

export interface CreateTechPayload {
  name: string;
  phone: string;
  email: string;
  home_base_lat: number;
  home_base_lon: number;
  years_experience: number;
  customer_rating: number;
  on_time_rate: number;
  skills: { skill_id: string; name: string; category: string; level: number }[];
}
