/** Eyebrow + heading + lead, the standard opener for every landing section. */
import type { ReactNode } from "react";

interface SectionHeadProps {
  id?: string;
  eyebrow: string;
  title: ReactNode;
  lead?: ReactNode;
  align?: "left" | "center";
}

export function SectionHead({ id, eyebrow, title, lead, align = "left" }: SectionHeadProps) {
  return (
    <div className={`section-head reveal ${align === "center" ? "is-center" : ""}`}>
      <p className="caption">{eyebrow}</p>
      <h2 id={id} className="h2">
        {title}
      </h2>
      {lead && <p className="lead">{lead}</p>}
    </div>
  );
}
