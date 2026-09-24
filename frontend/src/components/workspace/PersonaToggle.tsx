/**
 * PersonaToggle: spec §1.3. A visible, persistent segmented control in the
 * header. Switching is a pure view-layer change: session data is untouched.
 */
import type { Persona } from "../../state/sessionTypes";
import "./PersonaToggle.css";

interface PersonaToggleProps {
  persona: Persona;
  onChange(p: Persona): void;
}

const OPTIONS: Array<{ id: Persona; label: string; hint: string }> = [
  { id: "beginner", label: "Beginner", hint: "Plain-English explanations, guided flow" },
  { id: "expert", label: "Expert", hint: "Raw JSON, seed control, full metrics" },
];

export function PersonaToggle({ persona, onChange }: PersonaToggleProps) {
  return (
    <div className="persona" role="radiogroup" aria-label="Persona">
      {OPTIONS.map((o) => (
        <button
          key={o.id}
          type="button"
          role="radio"
          aria-checked={persona === o.id}
          title={o.hint}
          className={`persona-opt ${persona === o.id ? "is-active" : ""}`}
          onClick={() => onChange(o.id)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
              e.preventDefault();
              onChange(persona === "beginner" ? "expert" : "beginner");
            }
          }}
          tabIndex={persona === o.id ? 0 : -1}
        >
          {o.label}
        </button>
      ))}
      <span className={`persona-thumb ${persona === "expert" ? "is-right" : ""}`} aria-hidden="true" />
    </div>
  );
}
