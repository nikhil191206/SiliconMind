/**
 * Accessible modal dialog built on the native <dialog> element (focus trap,
 * Esc-to-close and inert background come for free).
 */
import { useEffect, useRef, type ReactNode } from "react";
import { Icon } from "./Icon";
import "./Modal.css";

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}

export function Modal({ open, title, onClose, children, footer, width = 520 }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="modal"
      style={{ width: `min(${width}px, calc(100vw - 32px))` }}
      aria-labelledby="modal-title"
      onClose={onClose}
      onClick={(e) => {
        // Click on the backdrop (the dialog element itself) closes.
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-inner">
        <header className="modal-head">
          <h2 id="modal-title" className="h5">
            {title}
          </h2>
          <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Close">
            <Icon name="x" />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </dialog>
  );
}
