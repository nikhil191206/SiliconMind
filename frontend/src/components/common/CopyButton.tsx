/** Copy-to-clipboard button with a transient "Copied" confirmation. */
import { useState } from "react";
import { Icon } from "./Icon";

interface CopyButtonProps {
  getText: () => string;
  label?: string;
  className?: string;
}

export function CopyButton({ getText, label = "Copy", className = "btn btn-secondary btn-sm" }: CopyButtonProps) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(getText());
      setState("copied");
    } catch {
      setState("failed");
    }
    window.setTimeout(() => setState("idle"), 1600);
  }

  return (
    <button type="button" className={className} onClick={copy} aria-live="polite">
      <Icon name={state === "copied" ? "check" : "copy"} size={14} />
      {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : label}
    </button>
  );
}
