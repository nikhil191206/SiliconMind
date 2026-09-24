/**
 * NetlistUploader: spec §3.1 (expert path).
 *
 * Drag-and-drop + explicit file picker. Accepts .v (→ rtl_code) and .json
 * (Yosys JSON → yosys_json_data). LEF/DEF are shown but disabled with the
 * honest "not yet available via this endpoint" message (§14.1).
 * Client-side pre-validation catches obvious mistakes; backend 400/422
 * messages remain the source of truth and are shown verbatim.
 */
import { useRef, useState } from "react";
import { formatBytes } from "../../../lib/format";
import { validateUpload, type UploadCheck } from "../../../lib/validation";
import { useSession } from "../../../state/SessionProvider";
import { Icon } from "../../common/Icon";
import { DesignNameField, designNameError } from "./DesignNameField";

export interface UploadState {
  file: { name: string; size: number; text: string } | null;
  check: UploadCheck | null;
  designName: string;
}

function suggestName(fileName: string, text: string): string | null {
  const m = /\bmodule\s+([A-Za-z_][A-Za-z0-9_]*)/.exec(text);
  if (m) return m[1];
  const base = fileName.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9_\-.]/g, "_");
  return /^[A-Za-z_]/.test(base) ? base : null;
}

export function NetlistUploader({ upload, setUpload }: { upload: UploadState; setUpload(u: UploadState): void }) {
  const { state, actions } = useSession();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [validating, setValidating] = useState(false);
  const [touched, setTouched] = useState(false);
  const busy = state.inFlight?.kind === "synthesize";

  async function accept(file: File) {
    setValidating(true);
    try {
      const text = await file.text();
      const check = validateUpload(file.name, file.size, text);
      setUpload({ ...upload, file: { name: file.name, size: file.size, text }, check });
    } finally {
      setValidating(false);
    }
  }

  async function submit() {
    setTouched(true);
    const f = upload.file;
    const c = upload.check;
    if (!f || !c?.ok || designNameError(upload.designName)) return;
    const design_name = upload.designName.trim();
    if (c.kind === "verilog") {
      await actions.synthesize({ design_name, rtl_code: f.text });
    } else if (c.kind === "yosys_json") {
      await actions.synthesize({ design_name, yosys_json_data: c.json });
    } else if (c.kind === "circuit_graph_json") {
      await actions.synthesize({ design_name, yosys_json_data: c.json });
    }
  }

  const graphJsonLive = upload.check?.kind === "circuit_graph_json" && !state.demoMode;
  const canSubmit = !!upload.check?.ok && !busy && !graphJsonLive;

  return (
    <div className="stack" style={{ ["--stack-gap" as string]: "16px" }}>
      <div
        className={`dropzone ${dragging ? "is-dragging" : ""} ${upload.file ? "has-file" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files[0];
          if (f) void accept(f);
        }}
      >
        {validating ? (
          <div className="dropzone-inner" role="status">
            <span className="spinner" />
            <p>Checking file…</p>
          </div>
        ) : upload.file ? (
          <div className="dropzone-file">
            <Icon name="file" size={20} />
            <div>
              <p className="mono">{upload.file.name}</p>
              <p className="hint">{formatBytes(upload.file.size)}</p>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => inputRef.current?.click()} disabled={busy}>
              Replace
            </button>
          </div>
        ) : (
          <div className="dropzone-inner">
            <span className="dropzone-icon">
              <Icon name="upload" size={20} />
            </span>
            <p>
              <strong>Drop a netlist here</strong> or{" "}
              <button type="button" className="link-btn" onClick={() => inputRef.current?.click()}>
                browse
              </button>
            </p>
            <div className="dropzone-types">
              <span className="badge">.v structural Verilog</span>
              <span className="badge">.json Yosys JSON</span>
              <span className="badge dropzone-disabled" title="Not yet available via /api/intake/synthesize">
                .lef / .def (coming soon)
              </span>
            </div>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".v,.sv,.json,.lef,.def"
          className="visually-hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void accept(f);
            e.target.value = "";
          }}
          aria-label="Choose netlist file"
        />
      </div>

      {upload.check && (
        <p className={`upload-check ${upload.check.ok ? "is-ok" : "is-bad"}`} role={upload.check.ok ? "status" : "alert"}>
          <Icon name={upload.check.ok ? "check" : "alertTriangle"} size={14} />
          {upload.check.message}
          {upload.check.ok && " Final validation happens on the backend."}
        </p>
      )}
      {graphJsonLive && (
        <p className="upload-check is-bad" role="alert">
          <Icon name="alertTriangle" size={14} />
          The live /api/intake/synthesize endpoint takes RTL or Yosys JSON, not a CircuitGraph. Loading a CircuitGraph
          directly is only available in Demo mode.
        </p>
      )}

      <DesignNameField
        value={upload.designName}
        onChange={(v) => setUpload({ ...upload, designName: v })}
        showError={touched}
        suggestion={upload.file ? suggestName(upload.file.name, upload.file.text) : null}
      />

      <div className="row">
        <button type="button" className="btn btn-primary" onClick={submit} disabled={!canSubmit}>
          <Icon name="cpu" size={14} /> {upload.check?.kind === "verilog" ? "Synthesize netlist" : "Import netlist"}
        </button>
        <span className="hint">
          {upload.check?.kind === "yosys_json" ? "Fast path: skips synthesis and parses the Yosys JSON directly." : ""}
        </span>
      </div>
    </div>
  );
}
