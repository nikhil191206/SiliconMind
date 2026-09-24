/**
 * Required design_name input (spec §3.1). It becomes part of permanent output
 * artifacts, so it's never silently defaulted: the user always sees and
 * confirms it. Restricted to identifier-safe characters.
 */
import { useId } from "react";

export const DESIGN_NAME_RE = /^[A-Za-z_][A-Za-z0-9_\-.]{0,63}$/;

export function designNameError(name: string): string | null {
  if (!name.trim()) return "A design name is required. It's used in every output (PlacementJSON, DEF export, run names).";
  if (!DESIGN_NAME_RE.test(name.trim()))
    return "Use letters, digits, _ - . only, starting with a letter or underscore (max 64).";
  return null;
}

interface DesignNameFieldProps {
  value: string;
  onChange(v: string): void;
  showError: boolean;
  suggestion?: string | null;
}

export function DesignNameField({ value, onChange, showError, suggestion }: DesignNameFieldProps) {
  const id = useId();
  const err = designNameError(value);
  return (
    <div className="field">
      <label className="label" htmlFor={id}>
        Design name <span className="faint">(required)</span>
      </label>
      <input
        id={id}
        className="input input-mono"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="e.g. alu16_top"
        aria-invalid={showError && !!err}
        aria-describedby={`${id}-hint`}
        spellCheck={false}
      />
      <span id={`${id}-hint`} className={`hint ${showError && err ? "field-error" : ""}`}>
        {showError && err ? (
          err
        ) : suggestion && !value ? (
          <>
            Suggested from your file:{" "}
            <button type="button" className="link-btn mono" onClick={() => onChange(suggestion)}>
              {suggestion}
            </button>
          </>
        ) : (
          "Keys every output of this session: CircuitGraph.design_name, PlacementJSON.design_name."
        )}
      </span>
    </div>
  );
}
