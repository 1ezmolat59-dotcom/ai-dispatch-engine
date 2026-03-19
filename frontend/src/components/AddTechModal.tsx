import { useState } from "react";
import { X } from "lucide-react";
import { api, type CreateTechPayload } from "../api/client";

interface Props { onClose: () => void; onCreated: () => void }

const PRESET_SKILLS = [
  { skill_id: "hvac", name: "hvac", category: "hvac", level: 3 },
  { skill_id: "refrig", name: "refrigerant_handling", category: "hvac", level: 2 },
  { skill_id: "plumb", name: "plumbing", category: "plumbing", level: 3 },
  { skill_id: "drain", name: "drain_cleaning", category: "plumbing", level: 2 },
  { skill_id: "elec", name: "electrical", category: "electrical", level: 3 },
  { skill_id: "panel", name: "panel_upgrade", category: "electrical", level: 2 },
  { skill_id: "gen_maint", name: "general_maintenance", category: "general", level: 2 },
  { skill_id: "insp", name: "inspection", category: "general", level: 2 },
];

export function AddTechModal({ onClose, onCreated }: Props) {
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    name: "", phone: "+15550000001", email: "tech@demo.com",
    home_base_lat: 40.7128, home_base_lon: -74.006,
    years_experience: 3, customer_rating: 4.5, on_time_rate: 0.9,
  });
  const [selectedSkills, setSelectedSkills] = useState<typeof PRESET_SKILLS>([]);

  const toggleSkill = (s: typeof PRESET_SKILLS[0]) => {
    setSelectedSkills(prev =>
      prev.find(x => x.skill_id === s.skill_id)
        ? prev.filter(x => x.skill_id !== s.skill_id)
        : [...prev, s]
    );
  };

  const submit = async () => {
    if (!form.name) { alert("Name required"); return; }
    if (!selectedSkills.length) { alert("Select at least one skill"); return; }
    setLoading(true);
    try {
      const payload: CreateTechPayload = {
        name: form.name, phone: form.phone, email: form.email,
        home_base_lat: Number(form.home_base_lat), home_base_lon: Number(form.home_base_lon),
        years_experience: Number(form.years_experience),
        customer_rating: Number(form.customer_rating),
        on_time_rate: Number(form.on_time_rate),
        skills: selectedSkills,
      };
      await api.createTech(payload);
      onCreated(); onClose();
    } catch (e) { alert(`Failed: ${e}`); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-slate-700">
          <h2 className="font-semibold text-white">Add Technician</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-3">
            {[
              ["name", "Name", "text"],
              ["phone", "Phone", "text"],
              ["email", "Email", "email"],
              ["years_experience", "Years Experience", "number"],
              ["customer_rating", "Rating (1-5)", "number"],
              ["on_time_rate", "On-time Rate (0-1)", "number"],
              ["home_base_lat", "Home Base Lat", "number"],
              ["home_base_lon", "Home Base Lon", "number"],
            ].map(([k, label, type]) => (
              <div key={k}>
                <label className="block text-xs text-slate-400 mb-1">{label}</label>
                <input type={type} value={(form as Record<string, string | number>)[k]}
                  onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))}
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white" />
              </div>
            ))}
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-2">Skills (select all that apply)</label>
            <div className="flex flex-wrap gap-2">
              {PRESET_SKILLS.map(s => {
                const active = !!selectedSkills.find(x => x.skill_id === s.skill_id);
                return (
                  <button key={s.skill_id} onClick={() => toggleSkill(s)}
                    className={`px-2.5 py-1 rounded-lg text-xs border transition-colors ${
                      active
                        ? "bg-blue-600 border-blue-500 text-white"
                        : "bg-slate-900 border-slate-600 text-slate-400 hover:border-slate-500"
                    }`}>
                    {s.name}
                  </button>
                );
              })}
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
            {loading ? "Adding..." : "Add Technician"}
          </button>
        </div>
      </div>
    </div>
  );
}
