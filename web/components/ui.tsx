"use client";

import { useEffect, useRef } from "react";

export function PageHero({ eyebrow, title, description, actions }: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="ds-hero">
      <div><span className="ds-eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>
      {actions && <div className="ds-hero-actions">{actions}</div>}
    </header>
  );
}

export function MetricStrip({ items }: { items: { value: string | number; label: string }[] }) {
  return <div className={`ds-metrics metrics-${Math.min(items.length, 4)}`}>{items.map((item) => <div key={item.label}><strong>{item.value}</strong><span>{item.label}</span></div>)}</div>;
}

export function StatusBadge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "success" | "warning" | "danger" | "info" }) {
  return <span className={`ds-status status-${tone}`}>{children}</span>;
}

export function EmptyState({ icon = "◇", title, description, action }: { icon?: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="ds-empty"><span className="ds-empty-icon">{icon}</span><h2>{title}</h2><p>{description}</p>{action}</div>;
}

export function LoadingGrid({ count = 4 }: { count?: number }) {
  return <div className="ds-card-grid" aria-label="Loading"><>{Array.from({ length: count }, (_, index) => <div className="ds-skeleton-card" key={index} />)}</></div>;
}

export function Drawer({ open, title, subtitle, onClose, children, footer }: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) { if (event.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKeyDown);
    return () => { window.removeEventListener("keydown", onKeyDown); previous?.focus(); };
  }, [onClose, open]);
  if (!open) return null;
  return <div className="ds-drawer-layer"><button className="ds-drawer-backdrop" aria-label="Close panel" onClick={onClose} /><aside className="ds-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"><header><div><span>{subtitle}</span><h2 id="drawer-title">{title}</h2></div><button ref={closeRef} type="button" aria-label="Close panel" onClick={onClose}>×</button></header><div className="ds-drawer-body">{children}</div>{footer && <footer>{footer}</footer>}</aside></div>;
}

export function ConfirmDialog({ open, title, description, confirmLabel = "Delete", onConfirm, onClose }: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) { if (event.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);
  if (!open) return null;
  return <div className="ds-modal-layer"><button className="ds-modal-backdrop" aria-label="Cancel" onClick={onClose} /><div className="ds-confirm" role="alertdialog" aria-modal="true"><span className="ds-confirm-icon">!</span><h2>{title}</h2><p>{description}</p><div><button className="btn btn-secondary" onClick={onClose}>Cancel</button><button className="btn btn-danger" onClick={onConfirm}>{confirmLabel}</button></div></div></div>;
}
