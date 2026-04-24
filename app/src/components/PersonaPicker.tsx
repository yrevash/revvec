import type { Persona } from "../lib/api";
import { Hammer, GraduationCap, ShieldCheck, Gauge } from "lucide-react";

const PERSONAS: { key: Persona; label: string; Icon: React.ComponentType<{ size?: number }> }[] = [
  { key: "new_hire",      label: "New hire",      Icon: GraduationCap },
  { key: "maintenance",   label: "Maintenance",   Icon: Hammer },
  { key: "quality",       label: "Quality",       Icon: ShieldCheck },
  { key: "plant_manager", label: "Plant manager", Icon: Gauge },
];

export function PersonaPicker({
  active,
  onChange,
}: {
  active: Persona;
  onChange: (p: Persona) => void;
}) {
  return (
    <div className="flex gap-1 p-1 bg-surface-deep rounded-full text-sm">
      {PERSONAS.map(({ key, label, Icon }) => {
        const isActive = key === active;
        return (
          <button
            key={key}
            onClick={() => onChange(key)}
            aria-pressed={isActive}
            className={
              "flex items-center gap-2 px-4 py-1.5 rounded-full transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 " +
              (isActive
                ? "bg-white text-ink shadow-card"
                : "text-muted hover:text-ink")
            }
          >
            <Icon size={14} />
            <span className="font-medium">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
