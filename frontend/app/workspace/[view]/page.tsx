"use client";
import { useParams } from "next/navigation";
import { WorkspaceShell } from "@/components/workspace-shell";
import { WorkspaceView } from "@/components/workspace-view";
export default function WorkspacePage(){ const params = useParams<{view:string}>(); return <WorkspaceShell><WorkspaceView view={params.view}/></WorkspaceShell>; }
