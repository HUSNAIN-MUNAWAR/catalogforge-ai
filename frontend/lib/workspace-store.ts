"use client";
import { create } from "zustand";
import type { Workspace } from "./api";

type WorkspaceState = { workspace?: Workspace; setWorkspace: (workspace: Workspace) => void };
export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  workspace: undefined,
  setWorkspace: (workspace) => {
    if (typeof window !== "undefined") window.localStorage.setItem("catalogforge.workspace", workspace.id);
    set({ workspace });
  },
}));
