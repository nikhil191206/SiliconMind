/**
 * EditInstructionBox: spec §6.1 + §5.4 selection convenience.
 *
 * Persistent box next to the canvas. If macros are selected, the user can
 * reference them ("Use selection"), this only rewrites the free-text
 * instruction (e.g. "macros 3, 5: …"); /api/placement/edit still receives a
 * plain-English `instruction` string, as the endpoint requires.
 *
 * On clarification the text stays in the box so it can be amended (§6.2).
 */
import { useEffect, useRef } from "react";
import { Icon } from "../../common/Icon";

interface EditInstructionBoxProps {
  value: string;
  onChange(v: string): void;
  selection: number[];
  onSubmit(text: string): void;
  busy: boolean;
  disabledReason: string | null;
  persona: "beginner" | "expert";
}

const SUGGESTIONS = [
  "move {sel} toward the left edge",
  "move {sel} away from macro 0",
  "move {sel} to the center",
];

export function selectionPhrase(selection: number[]): string {
  if (selection.length === 0) return "macro 0";
  if (selection.length === 1) return `macro ${selection[0]}`;
  return `macros ${selection.slice(0, 12).join(", ")}${selection.length > 12 ? ` (+${selection.length - 12} more)` : ""}`;
}

export function EditInstructionBox({ value, onChange, selection, onSubmit, busy, disabledReason, persona }: EditInstructionBoxProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    // Keep caret at the end after programmatic inserts.
    const el = ref.current;
    if (el && document.activeElement === el) el.setSelectionRange(el.value.length, el.value.length);
  }, [value]);

  const disabled = busy || !!disabledReason;
  const submit = () => {
    const t = value.trim();
    if (t && !disabled) onSubmit(t);
  };

  function insertSelection() {
    const phrase = selectionPhrase(selection);
    onChange(value.trim() ? `${value.trim()} ${phrase}` : `move ${phrase} `);
    ref.current?.focus();
  }

  return (
    <section className="editbox" aria-labelledby="editbox-title">
      <label id="editbox-title" htmlFor="editbox-input" className="editbox-label">
        <Icon name="message" size={14} /> Tell it what to change
      </label>
      <div className={`editbox-field ${disabled ? "is-disabled" : ""}`}>
        <textarea
          id="editbox-input"
          ref={ref}
          className="editbox-input"
          rows={2}
          value={value}
          placeholder={
            persona === "beginner"
              ? "e.g. move macro 3 toward the left edge"
              : "e.g. move macros 3, 5 away from macro 0 · keep m2 out of the top edge"
          }
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={disabled}
          aria-describedby="editbox-hint"
        />
        <button
          type="button"
          className="btn btn-primary btn-icon editbox-send"
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Send instruction"
        >
          {busy ? <span className="spinner editbox-spin" /> : <Icon name="send" size={15} />}
        </button>
      </div>
      <div className="editbox-meta">
        {selection.length > 0 ? (
          <button type="button" className="chip" onClick={insertSelection} disabled={disabled}>
            <Icon name="plus" size={11} /> Use selection ({selectionPhrase(selection)})
          </button>
        ) : (
          SUGGESTIONS.slice(0, 2).map((s) => (
            <button
              key={s}
              type="button"
              className="chip"
              onClick={() => onChange(s.replace("{sel}", selectionPhrase(selection)))}
              disabled={disabled}
            >
              {s.replace("{sel}", "macro …")}
            </button>
          ))
        )}
      </div>
      <p id="editbox-hint" className="hint">
        {disabledReason ?? (
          <>
            <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> new line. Everything you don't mention stays
            frozen.
          </>
        )}
      </p>
    </section>
  );
}
