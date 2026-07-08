"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Search, X } from "./icons";
import { client, type SearchItem } from "@/lib/api";

const actions = [
  ["Upload supplier file", "/workspace/source-intake"], ["Open Intake Inbox", "/workspace/intake"], ["Open Review Queue", "/workspace/review"], ["Open Duplicate Resolution", "/workspace/duplicates"], ["Open Product Master", "/workspace/product-master"], ["Open Vendor Quality", "/workspace/vendors"], ["Open Taxonomy Studio", "/workspace/taxonomy"], ["Open Publish Center", "/workspace/publish"], ["Create change set", "/workspace/change-sets"], ["Generate report", "/workspace/reports"], ["Operations pipeline", "/workspace/pipeline"], ["Launch readiness", "/workspace/launch"], ["Switch workspace", "/workspace/dashboard"],
];

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchItem[]>([]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler);
  }, [onClose]);
  useEffect(() => {
    const timer = window.setTimeout(() => { if (query.trim().length >= 2) client.search(query).then((data) => setResults(data.items)).catch(() => setResults([])); else setResults([]); }, 180);
    return () => window.clearTimeout(timer);
  }, [query]);
  if (!open) return null;
  const filtered = actions.filter(([label]) => label.toLowerCase().includes(query.toLowerCase())).slice(0, 6);
  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={onClose}><div className="command-palette" onMouseDown={(e) => e.stopPropagation()}><div className="command-input"><Search size={17}/><input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products, vendors, documents, or actions…" /><button className="btn btn-ghost" onClick={onClose}><X size={16}/></button></div><div className="command-section">Quick actions</div>{filtered.map(([label, href]) => <Link key={label} href={href} onClick={onClose} className="command-row"><span>{label}</span><kbd>↵</kbd></Link>)}{results.length > 0 && <><div className="command-section">Workspace results</div>{results.map((item) => <Link key={`${item.type}-${item.id}`} href={item.href} onClick={onClose} className="command-row"><div><b>{item.label}</b><span>{item.type} · {item.metadata}</span></div><kbd>↵</kbd></Link>)}</>}<div className="command-hint">⌘ K or Ctrl K · Search respects your active workspace.</div></div></div>;
}
