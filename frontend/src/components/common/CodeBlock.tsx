/**
 * Read-only, syntax-highlighted code using real <pre><code> semantics
 * (spec §10), with line numbers and an optional copy button.
 */
import { useMemo } from "react";
import { tokenizeVerilog } from "../../lib/highlight";
import { CopyButton } from "./CopyButton";
import "./CodeBlock.css";

interface CodeBlockProps {
  code: string;
  language: "verilog" | "text";
  label?: string;
  maxHeight?: number;
}

export function CodeBlock({ code, language, label, maxHeight = 420 }: CodeBlockProps) {
  const tokens = useMemo(() => (language === "verilog" ? tokenizeVerilog(code) : null), [code, language]);
  const lines = code.split("\n").length;
  return (
    <figure className="codeblock">
      <figcaption className="codeblock-bar">
        <span className="mono">{label ?? language}</span>
        <span className="faint mono">{lines} lines</span>
        <CopyButton getText={() => code} className="btn btn-ghost btn-sm codeblock-copy" />
      </figcaption>
      <div className="codeblock-scroll" style={{ maxHeight }}>
        <div className="codeblock-gutter mono" aria-hidden="true">
          {Array.from({ length: lines }, (_, i) => (
            <span key={i}>{i + 1}</span>
          ))}
        </div>
        <pre className="codeblock-pre">
          <code>
            {tokens
              ? tokens.map((t, i) =>
                  t.kind === "plain" ? (
                    t.text
                  ) : (
                    <span key={i} className={`tok-${t.kind}`}>
                      {t.text}
                    </span>
                  ),
                )
              : code}
          </code>
        </pre>
      </div>
    </figure>
  );
}
