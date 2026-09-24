/**
 * Collapsible, syntax-highlighted JSON tree (spec §7.1). Renders inside
 * <pre><code> for assistive tech; large arrays are paged ("show 100 more")
 * so a 900k-entry placements array doesn't lock the tab.
 */
import { useState } from "react";
import "./JsonTree.css";

const PAGE = 100;

function Primitive({ value }: { value: unknown }) {
  if (value === null) return <span className="tok-bool">null</span>;
  if (typeof value === "string") return <span className="tok-str">"{value}"</span>;
  if (typeof value === "number") return <span className="tok-num">{String(value)}</span>;
  if (typeof value === "boolean") return <span className="tok-bool">{String(value)}</span>;
  return <span>{String(value)}</span>;
}

function Node({ name, value, depth, defaultOpen }: { name: string | null; value: unknown; depth: number; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [shown, setShown] = useState(PAGE);
  const isArr = Array.isArray(value);
  const isObj = value !== null && typeof value === "object";
  const key = name !== null ? (
    <>
      <span className="tok-key">"{name}"</span>
      <span className="tok-punc">: </span>
    </>
  ) : null;

  if (!isObj) {
    return (
      <div className="jt-row" style={{ paddingLeft: depth * 14 }}>
        {key}
        <Primitive value={value} />
      </div>
    );
  }

  const entries: Array<[string, unknown]> = isArr
    ? (value as unknown[]).slice(0, shown).map((v, i) => [String(i), v])
    : Object.entries(value as Record<string, unknown>);
  const total = isArr ? (value as unknown[]).length : entries.length;
  const [openB, closeB] = isArr ? ["[", "]"] : ["{", "}"];

  return (
    <div>
      <div className="jt-row" style={{ paddingLeft: depth * 14 }}>
        <button
          type="button"
          className="jt-toggle"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-label={`${open ? "Collapse" : "Expand"} ${name ?? "root"}`}
        >
          {open ? "▾" : "▸"}
        </button>
        {key}
        <span className="tok-punc">{openB}</span>
        {!open && (
          <>
            <span className="jt-summary"> {isArr ? `${total} items` : `${total} keys`} </span>
            <span className="tok-punc">{closeB}</span>
          </>
        )}
      </div>
      {open && (
        <>
          {entries.map(([k, v]) => (
            <Node key={k} name={isArr ? null : k} value={v} depth={depth + 1} defaultOpen={depth < 0} />
          ))}
          {isArr && shown < total && (
            <div className="jt-row" style={{ paddingLeft: (depth + 1) * 14 }}>
              <button type="button" className="jt-more" onClick={() => setShown((s) => s + PAGE * 10)}>
                … {total - shown} more, show {Math.min(PAGE * 10, total - shown)}
              </button>
            </div>
          )}
          <div className="jt-row" style={{ paddingLeft: depth * 14 }}>
            <span className="tok-punc">{closeB}</span>
          </div>
        </>
      )}
    </div>
  );
}

export function JsonTree({ value, label }: { value: unknown; label: string }) {
  return (
    <pre className="jt" aria-label={label}>
      <code>
        <Node name={null} value={value} depth={0} defaultOpen />
      </code>
    </pre>
  );
}
