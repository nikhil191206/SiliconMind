/**
 * SeedControl: spec §7.2 (Expert only). Both /generate and /edit accept a
 * seed (default 0). Editable here; the seed that produced what's on screen is
 * shown separately from generation_metadata.seed.
 */
import { useId } from "react";
import { Icon } from "../../common/Icon";

interface SeedControlProps {
  seed: number;
  onChange(seed: number): void;
  disabled?: boolean;
  compact?: boolean;
}

export function SeedControl({ seed, onChange, disabled, compact }: SeedControlProps) {
  const id = useId();
  return (
    <div className={`seed ${compact ? "is-compact" : ""}`}>
      <label htmlFor={id} className={compact ? "visually-hidden" : "label"}>
        Seed for next request
      </label>
      <div className="seed-row">
        <span className="seed-prefix mono" aria-hidden="true">
          seed
        </span>
        <input
          id={id}
          type="number"
          min={0}
          step={1}
          className="input input-mono seed-input"
          value={seed}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
        />
        <button
          type="button"
          className="btn btn-secondary btn-icon btn-sm"
          disabled={disabled}
          onClick={() => onChange(Math.floor(Math.random() * 100_000))}
          aria-label="Random seed"
          title="Random seed"
        >
          <Icon name="dice" size={14} />
        </button>
      </div>
    </div>
  );
}
