/** One node of the read-only workflow canvas. Mirrors `project_model.workflow_canvas`. */
export type WorkflowNodeKind =
  | 'DISCOVERY'
  | 'RECORDER'
  | 'STUDIO'
  | 'RUN'
  | 'FAILURE'
  | 'FAILURE_ANALYSIS'
  | 'HUMAN_APPROVAL'
  | 'EXACT_VERIFICATION';

export type WorkflowStageKey =
  | 'discovery'
  | 'recorder'
  | 'studio'
  | 'run'
  | 'failure'
  | 'analysis'
  | 'approval'
  | 'verification';

export interface WorkflowEvidence {
  kind: string;
  label: string;
  ref: string | null;
  url: string | null;
}

/** Evidence the Discovery loop already collects, keyed by `state_id:collection`. */
export interface DiscoveryEvidenceRef {
  id: string;
  collection: string;
  page_url: string | null;
  captured_at: string | null;
  collection_method: string;
  artifact_ref: string | null;
  summary: Record<string, unknown>;
}

export interface DiscoveryMetrics {
  states: number;
  actions: number;
  features: number;
  requirements: number;
  gaps: number;
  covered: number;
  partial: number;
  not_covered: number;
  test_cases: number;
}

export interface WorkflowNode {
  id: string;
  kind: WorkflowNodeKind;
  stage: WorkflowStageKey;
  title: string;
  subtitle: string | null;
  status: string;
  entity_type: string;
  entity_id: string;
  task_id: string | null;
  parent_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  evidence: WorkflowEvidence[];
  links: Record<string, string>;
  metrics: DiscoveryMetrics | null;
  evidence_index: DiscoveryEvidenceRef[];
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
  label: string | null;
}

export interface WorkflowStage {
  key: WorkflowStageKey;
  title: string;
  kind: WorkflowNodeKind;
  description: string;
}

export interface WorkflowCanvas {
  project_id: string;
  generated_at: string;
  stages: WorkflowStage[];
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  counts: Record<string, number>;
  truncated: boolean;
}
