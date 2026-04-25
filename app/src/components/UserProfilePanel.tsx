import { useEffect, useState } from "react";
import { X, User, Trash2 } from "lucide-react";
import type { UserProfile } from "../lib/api";
import { EMPTY_PROFILE, isProfileSet } from "../lib/userProfile";

interface Field {
  key: keyof UserProfile;
  label: string;
  placeholder: string;
  multiline?: boolean;
}

const FIELDS: Field[] = [
  {
    key: "role",
    label: "Role",
    placeholder: "e.g. Maintenance Engineer · Quality Lead · New Hire",
  },
  {
    key: "experience",
    label: "Experience",
    placeholder: "e.g. 10 years on rover thermal subsystems",
  },
  {
    key: "focus",
    label: "Current focus",
    placeholder: "e.g. EDL anomalies · MEDA telemetry · CMAPSS prognostics",
  },
  {
    key: "preferences",
    label: "How you like answers",
    placeholder: "e.g. terse · cite procedures by ID · prefer SI units",
    multiline: true,
  },
  {
    key: "notes",
    label: "Other context",
    placeholder: "anything else the assistant should know about you",
    multiline: true,
  },
];

export function UserProfilePanel({
  open,
  initial,
  onClose,
  onSave,
  onClear,
}: {
  open: boolean;
  initial: UserProfile;
  onClose: () => void;
  onSave: (next: UserProfile) => void;
  onClear: () => void;
}) {
  const [draft, setDraft] = useState<UserProfile>(initial);

  useEffect(() => {
    if (open) setDraft(initial);
  }, [open, initial]);

  if (!open) return null;

  function setField(k: keyof UserProfile, v: string) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-6">
      <div className="bg-surface w-full max-w-xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-deep">
          <div className="flex items-center gap-2.5">
            <User size={16} className="text-accent" />
            <h2 className="text-[15px] font-semibold text-ink">Your profile</h2>
            {isProfileSet(draft) && (
              <span className="text-[10px] uppercase tracking-[0.08em] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
                active
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-surface-deep/60 text-muted hover:text-ink transition-colors"
            aria-label="close profile"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-6 py-4 text-[12.5px] text-muted leading-relaxed border-b border-surface-deep/60">
          Tell revvec who you are. The assistant will tailor every answer to your role
          and background, never inventing facts beyond your local sources, but
          emphasising parts most useful to you.
          <br />
          <span className="text-[11px] text-muted/80">
            Stored only in this app's local storage. Never leaves the machine.
          </span>
        </div>

        <div className="px-6 py-5 space-y-4 overflow-y-auto">
          {FIELDS.map((f) => (
            <label key={f.key} className="block">
              <div className="text-[11px] uppercase tracking-[0.08em] text-muted font-medium mb-1.5">
                {f.label}
              </div>
              {f.multiline ? (
                <textarea
                  value={(draft[f.key] ?? "") as string}
                  onChange={(e) => setField(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  rows={2}
                  className="w-full px-3 py-2 text-[13px] bg-surface-card border border-surface-deep rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/50 resize-none"
                />
              ) : (
                <input
                  value={(draft[f.key] ?? "") as string}
                  onChange={(e) => setField(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  className="w-full px-3 py-2 text-[13px] bg-surface-card border border-surface-deep rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/50"
                />
              )}
            </label>
          ))}
        </div>

        <div className="flex items-center justify-between px-6 py-3.5 border-t border-surface-deep bg-surface-card/50">
          <button
            onClick={() => {
              if (confirm("Clear your profile? This is local-only.")) {
                onClear();
                setDraft({ ...EMPTY_PROFILE });
              }
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] text-muted hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors"
          >
            <Trash2 size={12} /> clear
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-[12px] text-muted hover:text-ink transition-colors"
            >
              cancel
            </button>
            <button
              onClick={() => onSave(draft)}
              className="px-4 py-1.5 text-[12px] font-medium bg-ink text-white rounded-lg hover:bg-ink-soft transition-colors"
            >
              save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
