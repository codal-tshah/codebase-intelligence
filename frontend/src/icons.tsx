/** The one icon set (Lucide, 1.5 stroke). Node types and views map to icons here only. */
import {
  ArrowLeftRight,
  Box,
  Boxes,
  Braces,
  Cloud,
  Component,
  Database,
  File,
  FileCode2,
  FolderTree,
  Globe,
  History,
  Layers,
  LayoutDashboard,
  Link2,
  ListTree,
  Network,
  Route,
  Settings2,
  Table2,
  Waypoints,
  type LucideIcon,
  type LucideProps,
} from "lucide-react";

export const NODE_ICON: Record<string, LucideIcon> = {
  Project: FolderTree,
  Package: Boxes,
  Module: FileCode2,
  Class: Box,
  Function: Braces,
  Component: Component,
  Endpoint: Route,
  Middleware: Link2,
  Model: Database,
  Table: Table2,
  Field: ListTree,
  Migration: History,
  ExternalService: Cloud,
  ConfigRef: Settings2,
};

export const VIEW_ICON: Record<string, LucideIcon> = {
  layers: Layers,
  architecture: Network,
  "api-flow": Route,
  "call-graph": Waypoints,
  components: Component,
  er: Database,
  integrations: ArrowLeftRight,
  overview: LayoutDashboard,
};

export function NodeIcon({ type, ...props }: { type?: string | null } & Omit<LucideProps, "type">) {
  const Icon = (type && NODE_ICON[type]) || File;
  return <Icon size={14} strokeWidth={1.5} aria-hidden {...props} />;
}

export function ViewIcon({ id, ...props }: { id: string } & LucideProps) {
  const Icon = VIEW_ICON[id] ?? Globe;
  return <Icon size={16} strokeWidth={1.5} aria-hidden {...props} />;
}
