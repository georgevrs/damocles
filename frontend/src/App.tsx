// Three-column layout — Map · Brief · Graph — stacked above a bottom strip
// of ProgressStream + AuditLog. Every divide is now a draggable resize
// handle (react-resizable-panels): the analyst can grow the map for a
// situational read, then shrink it back to read a brief, without losing
// either side. Initial sizes match the v1 ratios (30 / 40 / 30) and a
// 65 / 35 vertical split.
//
// Persistence: panel sizes are saved per autoSaveId so each analyst keeps
// their own layout across reloads.

import {
  Panel, PanelGroup, PanelResizeHandle,
} from "react-resizable-panels";

import WatchInput     from "./components/WatchInput";
import MapPanel       from "./components/MapPanel";
import BriefPanel     from "./components/BriefPanel";
import GraphPanel     from "./components/GraphPanel";
import ProgressStream from "./components/ProgressStream";
import AuditLog       from "./components/AuditLog";
import EvidenceModal  from "./components/EvidenceModal";

// Resize handles — thin vertical/horizontal slivers that brighten on
// hover/active so the affordance is unmistakable without dominating the
// chrome. Tailwind data-* selectors come from the lib.
function VHandle() {
  return (
    <PanelResizeHandle
      className="group relative w-1 cursor-col-resize bg-panel-border data-[resize-handle-state=hover]:bg-threat-amber/60 data-[resize-handle-state=drag]:bg-threat-amber"
    >
      <div className="absolute left-1/2 top-1/2 h-10 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded bg-panel-border group-data-[resize-handle-state=hover]:bg-threat-amber/70 group-data-[resize-handle-state=drag]:bg-threat-amber" />
    </PanelResizeHandle>
  );
}

function HHandle() {
  return (
    <PanelResizeHandle
      className="group relative h-1 cursor-row-resize bg-panel-border data-[resize-handle-state=hover]:bg-threat-amber/60 data-[resize-handle-state=drag]:bg-threat-amber"
    >
      <div className="absolute left-1/2 top-1/2 h-[3px] w-10 -translate-x-1/2 -translate-y-1/2 rounded bg-panel-border group-data-[resize-handle-state=hover]:bg-threat-amber/70 group-data-[resize-handle-state=drag]:bg-threat-amber" />
    </PanelResizeHandle>
  );
}

export default function App() {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-panel-bg text-panel-text">
      <WatchInput />

      {/* Vertical: top columns | bottom strip */}
      <PanelGroup direction="vertical" autoSaveId="damocles.layout.v" className="flex-1">
        <Panel defaultSize={68} minSize={35}>
          {/* Horizontal: map | brief | graph */}
          <PanelGroup direction="horizontal" autoSaveId="damocles.layout.h">
            <Panel defaultSize={30} minSize={15} className="overflow-hidden">
              <MapPanel className="h-full w-full" />
            </Panel>
            <VHandle />
            <Panel defaultSize={40} minSize={20} className="overflow-hidden">
              <BriefPanel className="h-full w-full" />
            </Panel>
            <VHandle />
            <Panel defaultSize={30} minSize={15} className="overflow-hidden">
              <GraphPanel className="h-full w-full" />
            </Panel>
          </PanelGroup>
        </Panel>
        <HHandle />
        <Panel defaultSize={32} minSize={10} className="overflow-hidden">
          <PanelGroup direction="horizontal" autoSaveId="damocles.layout.bottom">
            <Panel defaultSize={50} minSize={20} className="overflow-hidden">
              <ProgressStream className="h-full w-full" />
            </Panel>
            <VHandle />
            <Panel defaultSize={50} minSize={20} className="overflow-hidden">
              <AuditLog className="h-full w-full" />
            </Panel>
          </PanelGroup>
        </Panel>
      </PanelGroup>

      <EvidenceModal />
    </div>
  );
}
