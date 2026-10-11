export const WORKSPACE_MIN_MAIN_WIDTH = 820;
export const WORKSPACE_STUDIO_MIN_MAIN_WIDTH = 960;

const WORKSPACE_CONTEXT_STACK_BREAKPOINT = 820;
const WORKSPACE_INSPECTOR_MODAL_BREAKPOINT = 1280;
const WORKSPACE_GRID_GAP = 12;
const WORKSPACE_CONTEXT_RESIZER_WIDTH = 5;
const WORKSPACE_INSPECTOR_MIN_WIDTH = 280;
const WORKSPACE_INSPECTOR_MAX_WIDTH = 640;

export interface WorkspacePanelModeInput {
  viewportWidth: number;
  workspaceWidth: number;
  contextOpen: boolean;
  contextWidth: number;
  inspectorWidth: number;
  isStudioView: boolean;
  isResultView: boolean;
}

export interface WorkspacePanelMode {
  contextCompact: boolean;
  stackContext: boolean;
  inspectorModal: boolean;
}

export function workspacePanelMode(input: WorkspacePanelModeInput): WorkspacePanelMode {
  const minMainWidth = input.isStudioView
    ? WORKSPACE_STUDIO_MIN_MAIN_WIDTH
    : WORKSPACE_MIN_MAIN_WIDTH;
  const contextTrackWidth = input.contextWidth
    + WORKSPACE_CONTEXT_RESIZER_WIDTH
    + 2 * WORKSPACE_GRID_GAP;
  const contextCompact = !input.isResultView && (
    input.viewportWidth <= 600 || input.workspaceWidth < contextTrackWidth + minMainWidth
  );
  const stackContext = input.viewportWidth <= WORKSPACE_CONTEXT_STACK_BREAKPOINT
    || (input.contextOpen && !input.isResultView && input.workspaceWidth < contextTrackWidth + minMainWidth);
  const horizontalContextWidth = input.contextOpen && !input.isResultView && !stackContext
    ? contextTrackWidth
    : 0;
  const sideInspectorWidth = Math.max(
    WORKSPACE_INSPECTOR_MIN_WIDTH,
    Math.min(input.inspectorWidth, WORKSPACE_INSPECTOR_MAX_WIDTH, input.viewportWidth * 0.32),
  );
  const inspectorModal = input.viewportWidth <= WORKSPACE_INSPECTOR_MODAL_BREAKPOINT
    || input.workspaceWidth < horizontalContextWidth + sideInspectorWidth + WORKSPACE_GRID_GAP + minMainWidth;

  return { contextCompact, stackContext, inspectorModal };
}
