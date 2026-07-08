"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Boxes, FileSearch, FolderInput, GitBranch, Grid2X2, History, PackageCheck, PanelRight, Settings2, Tags, UsersRound, Workflow, ShieldCheck, Sparkles, BarChart3, CircleAlert, Command, Database, Rocket } from "lucide-react";
import { client } from "@/lib/api";
import { useWorkspaceStore } from "@/lib/workspace-store";
import { CommandPalette } from "./command-palette";

const navigation = [
  { group: "Workspace", items: [["Overview", "dashboard", Grid2X2], ["Intake inbox", "intake", FolderInput], ["Source intake", "source-intake", FileSearch], ["Document intelligence", "documents", FileSearch], ["Product master", "product-master", Boxes], ["Product review", "review", PanelRight], ["Catalog grid", "catalog", Database], ["Duplicate resolution", "duplicates", GitBranch]] },
  { group: "Operations", items: [["Data quality", "quality", CircleAlert], ["Taxonomy & attributes", "taxonomy", Tags], ["Vendor quality", "vendors", UsersRound], ["Publish & reconciliation", "publish", PackageCheck], ["Change sets", "change-sets", History], ["Pipeline center", "pipeline", Workflow], ["Reports & alerts", "reports", BarChart3], ["Catalog intelligence", "intelligence", Sparkles]] },
  { group: "Governance", items: [["Lineage explorer", "lineage", History], ["Security & governance", "governance", ShieldCheck], ["Launch readiness", "launch", Rocket], ["Platform operations", "operations", Settings2]] },
] as const;

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const queryClient = useQueryClient();
  const { workspace, setWorkspace } = useWorkspaceStore();
  const [palette, setPalette] = useState(false);
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: client.me });
  useEffect(() => { if (me?.workspace && !workspace) setWorkspace(me.workspace); }, [me, workspace, setWorkspace]);
  useEffect(() => { const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setPalette(true); } }; window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler); }, []);
  const selected = workspace || me?.workspace;
  return <div className="workspace"><aside className="sidebar"><Link href="/" className="brand"><span className="brand-mark">CF</span><span><span className="brand-title">CatalogForge</span><span style={{ display: "block", fontSize: 10, color: "#6d756e", fontWeight: 700 }}>product-data operations</span></span></Link><span className="pill" style={{ alignSelf: "flex-start", margin: "0 7px", background: "#edf5ef", color: "#317152", borderColor: "#d3e7d7" }}><i className="icon-dot" /> Synthetic demo</span><label className="workspace-switcher"><span>Active workspace</span><select aria-label="Active workspace" value={selected?.id || ""} onChange={async (event) => { const target = me?.workspaces.find((item) => item.id === event.target.value); if (!target) return; await client.switchWorkspace(target.id); setWorkspace(target); queryClient.invalidateQueries(); }}><option value="">Loading…</option>{me?.workspaces.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><nav>{navigation.map((section) => <div key={section.group}><div className="nav-section">{section.group}</div>{section.items.map(([label, slug, Icon]) => <Link key={slug} className={`nav-link ${path === `/workspace/${slug}` ? "active" : ""}`} href={`/workspace/${slug}`}><Icon size={16}/><span>{label}</span></Link>)}</div>)}</nav><div className="sidebar-bottom"><button className="nav-link nav-button" onClick={() => setPalette(true)}><Command size={16}/><span>Command palette</span><b style={{ marginLeft: "auto", fontSize: 10, color: "#375edb" }}>⌘K</b></button><div style={{ padding: "10px", fontSize: 11, color: "#6d756e", lineHeight: 1.45 }}>All records, metrics, source files, reports, and connectors in this demo are synthetic or explicitly mocked.</div></div></aside><main className="main">{children}</main><CommandPalette open={palette} onClose={() => setPalette(false)} /></div>;
}
