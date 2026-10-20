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

export interface DiscoveryEvidenceMetrics {
  dom_elements: number;
  dom_elements_deduped: number;
  page_states: number;
  locators: number;
  locators_ambiguous: number;
  requests: number;
  requests_associated: number;
  actions: number;
  state_changes: number;
  scenarios: number;
  covered: number;
  candidate_gaps: number;
  undetermined: number;
  captured: boolean;
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
  evidence?: DiscoveryEvidenceMetrics | null;
}

/** One structured fact captured by a discovery run (`/discovery/runs/{id}/evidence`). */
export interface DiscoveryEvidence {
  evidence_id: string;
  kind: string;
  state_id: string | null;
  step_id: string | null;
  artifact_id: string | null;
  source: string;
  redacted: boolean;
  observed_at: string | null;
  dedupe_key: string;
  payload: Record<string, unknown>;
}

/** A candidate scenario and the coverage relation to existing test cases. */
export interface DiscoveryScenario {
  scenario_id: string;
  title: string;
  url_template: string | null;
  evidence_ids: string[];
  test_case_ids: string[];
  coverage_status: string;
  match_method: string | null;
  note: string | null;
}

export interface DiscoveryScenarioCollection {
  run_id: string;
  project_id: string;
  summary: Record<string, unknown>;
  scenarios: DiscoveryScenario[];
}

export interface DiscoveryCollectionSummary {
  run_id: string;
  project_id: string;
  capture_enabled: boolean;
  counts: Record<string, number>;
  analysis: {
    dom_element: { raw: number; deduped: number; filtered: number; stored: number };
    network_request: {
      raw: number;
      deduped: number;
      filtered: number;
      stored: number;
      by_resource: Record<string, number>;
      by_status: Record<string, number>;
      associated: number;
      unassociated: number;
      association_methods: Record<string, number>;
    };
    locator_candidate: {
      total: number;
      unique: number;
      verified: number;
      ambiguous: number;
      ambiguous_evidence_ids: string[];
    };
    user_action: { total: number; state_changed: number; no_state_change: number; with_requests: number };
    page_state: { total: number; fingerprints: string[] };
    screenshot: { total: number };
    filtered_breakdown: Record<string, number>;
    state_captures: number;
    measures: Record<string, string>;
  };
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
