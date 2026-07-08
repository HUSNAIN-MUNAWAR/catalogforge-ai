"use client";
import { Bell, ChevronDown, Search, Sparkles } from "./icons";
import { useState } from "react";
import { CommandPalette } from "./command-palette";
import { useQuery } from "@tanstack/react-query";
import { client } from "@/lib/api";
import { useWorkspaceStore } from "@/lib/workspace-store";
export function Topbar({ title, action }: { title: string; action?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const { workspace } = useWorkspaceStore();
  const { data } = useQuery({ queryKey: ["alerts"], queryFn: client.alerts });
  return <><div className="topbar"><div><div className="topbar-title">{title}</div><div className="topbar-meta"><span>CatalogForge AI</span><span>•</span><span>{workspace?.name || "Synthetic Demo Workspace"}</span><span className="badge badge-green">Synthetic demo</span></div></div><div style={{ display: "flex", alignItems: "center", gap: 9 }}><button className="btn btn-secondary" style={{ padding: "9px 10px" }} aria-label="Open command palette" onClick={() => setOpen(true)}><Search size={16}/></button><button className="btn btn-secondary" style={{ padding: "9px 10px" }} aria-label="Governed intelligence" title="Open governed Catalog Intelligence"><Sparkles size={16}/></button><button className="btn btn-secondary" style={{ padding: "9px 10px" }} aria-label="Notifications" title={`${data?.items.filter((item) => item.status === "Open").length || 0} open alerts`}><Bell size={16}/></button>{action}<button className="btn btn-secondary" style={{ padding: "8px 10px" }} title="Demo user"><span style={{ width: 22, height: 22, borderRadius: 8, background: "#e6ddcf", display: "grid", placeItems: "center", fontSize: 10 }}>AC</span><ChevronDown size={14}/></button></div></div><CommandPalette open={open} onClose={() => setOpen(false)} /></>;
}
