import { useState } from "react";
import { X } from "lucide-react";
import { api, type CreateJobPayload } from "../api/client";

const JOB_TYPES = [
  "hvac_repair", "hvac_install", "hvac_maintenance", "hvac_emergency", "hvac_diagnostic",
  "plumbing_repair", "plumbing_install", "plumbing_emergency", "drain_cleaning", "water_heater",
  "electrical_repair", "electrical_install", "electrical_inspection", "panel_upgrade", "ev_charger",
  "maintenance", "inspection", "estimate",
];

interface Props { onClose: () => void; onCreated: () => void }

export function AddJobModal({ onClose, onCreated }: Props) {
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    job_type: "hvac_repair",
    priority: 4,
    description: "",
    customer_name: "",
    customer_phone: "+15550000000",
    customer_email: "customer@demo.com",
    customer_address: "123 Main St, New York, NY",
    customer_lat: 40.7614 + (Math.random() - 0.5) * 0.1,
    customer_lon: -73.9776 + (Math.random() - 0.5) * 0.1,
    equipment_make: "",
    equipment_year: "",
  });

  const set = (k: string, v: string | number) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    setLoading(true);
    try {
      const payload: CreateJobPayload = {
        job_type: form.job_type,
        priority: Number(form.priority),
        description: form.description,
        customer: {
          customer_id: crypto.randomUUID(),
          name: form.customer_name || "Customer",
          phone: form.customer_phone,
          email: form.customer_email,
          address: form.customer_address,
          latitude: Number(form.customer_lat),
          longitude: Number(form.customer_lon),
        },
        equipment: form.equipment_make ? { make: form.equipment_make, year_installed: form.equipment_year ? Number(form.equipment_year) : undefined } : undefined,
      };
      await api.createJob(payload);
      onCreated();
      onClose();
    } catch (e) {
      alert(`Failed: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-slate-700">
          <h2 className="font-semibold text-white">New Dispatch Job</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Job Type</label>
              <select value={form.job_type} onChange={e => set("job_type", e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white">
                {JOB_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Priority</label>
              <select value={form.priority} onChange={e => set("priority", Number(e.target.value))}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white">
                <option value={1}>🚨 Emergency</option>
                <option value={2}>⚡ Urgent</option>
                <option value={3}>▲ High</option>
                <option value={4}>Normal</option>
                <option value={5}>Low</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Description</label>
            <textarea value={form.description} onChange={e => set("description", e.target.value)}
              rows={2} className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white resize-none"
              placeholder="Describe the issue..." />
          </div>

          <div className="border-t border-slate-700 pt-3">
            <div className="text-xs text-slate-500 uppercase tracking-wide mb-2">Customer</div>
            <div className="grid grid-cols-2 gap-3">
              {[
                ["customer_name", "Name", "text"],
                ["customer_phone", "Phone", "text"],
                ["customer_email", "Email", "email"],
                ["customer_address", "Address", "text"],
                ["customer_lat", "Latitude", "number"],
                ["customer_lon", "Longitude", "number"],
              ].map(([key, label, type]) => (
                <div key={key}>
                  <label className="block text-xs text-slate-400 mb-1">{label}</label>
                  <input type={type} value={(form as Record<string, string | number>)[key]}
                    onChange={e => set(key, e.target.value)}
                    className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white" />
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-slate-700 pt-3">
            <div className="text-xs text-slate-500 uppercase tracking-wide mb-2">Equipment (optional)</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Make</label>
                <input value={form.equipment_make} onChange={e => set("equipment_make", e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white"
                  placeholder="e.g. Carrier" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Year Installed</label>
                <input type="number" value={form.equipment_year} onChange={e => set("equipment_year", e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white"
                  placeholder="e.g. 2012" />
              </div>
            </div>
          </div>
        </div>

        <div className="flex gap-3 p-5 border-t border-slate-700">
          <button onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-700 transition-colors">
            Cancel
          </button>
          <button onClick={submit} disabled={loading}
            className="flex-1 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors">
            {loading ? "Creating..." : "Create Job"}
          </button>
        </div>
      </div>
    </div>
  );
}
