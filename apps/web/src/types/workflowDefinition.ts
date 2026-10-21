/** Mirror of the authoring contract in `packages/project-model/project_model/workflow_definition.py`. */
export interface WorkflowNodeInput {
  name: string;
  kind: 'string' | 'integer' | 'boolean' | 'list';
  required: boolean;
  description: string;
}

export interface WorkflowCatalogueEntry {
  kind: string;
  title: string;
  risk: 'READ' | 'PROPOSE' | 'APPROVAL' | 'WRITE' | 'EXECUTE';
  summary: string;
  writes: boolean;
  inputs: WorkflowNodeInput[];
}

export interface WorkflowNodeSpec {
  key: string;
  kind: string;
  title?: string;
  inputs?: Record<string, unknown>;
  position?: { x: number; y: number } | null;
}

export interface WorkflowEdgeSpec {
  source: string;
  target: string;
}

export interface WorkflowGraphSpec {
  nodes: WorkflowNodeSpec[];
  edges: WorkflowEdgeSpec[];
}

export interface WorkflowIssue {
  code: string;
  message: string;
  node_key?: string | null;
}

export interface WorkflowVersionSummary {
  id: string;
  version: number;
  state: 'DRAFT' | 'PUBLISHED';
  checksum: string;
  issues: WorkflowIssue[];
  created_by: string | null;
  created_at: string | null;
  published_by: string | null;
  published_at: string | null;
  node_count: number;
  edge_count: number;
  graph?: WorkflowGraphSpec;
}

export interface WorkflowDefinitionSummary {
  id: string;
  project_id: string;
  name: string;
  description: string;
  published_version: number | null;
  draft_version: number | null;
  draft_node_count: number;
  draft_issues: WorkflowIssue[];
  updated_at: string | null;
}

export interface WorkflowDefinitionDetail extends WorkflowDefinitionSummary {
  draft: {
    version: number | null;
    checksum: string | null;
    graph: WorkflowGraphSpec;
    issues: WorkflowIssue[];
  };
  published: WorkflowVersionSummary | null;
  versions: WorkflowVersionSummary[];
  catalogue: WorkflowCatalogueEntry[];
}

export interface WorkflowDefinitionList {
  definitions: WorkflowDefinitionSummary[];
  catalogue: WorkflowCatalogueEntry[];
}

export interface WorkflowGraphDiff {
  nodes: {
    added: WorkflowNodeSpec[];
    removed: WorkflowNodeSpec[];
    changed: { key: string; fields: string[]; before: WorkflowNodeSpec; after: WorkflowNodeSpec }[];
  };
  edges: {
    added: WorkflowEdgeSpec[];
    removed: WorkflowEdgeSpec[];
  };
  identical: boolean;
}

export interface WorkflowVersionComparison {
  definition_id: string;
  base: WorkflowVersionSummary;
  head: WorkflowVersionSummary;
  diff: WorkflowGraphDiff;
}

export interface WorkflowExecutionDiffRow {
  key: string;
  kind: string;
  step_key: string;
  step_id: string;
  status: string;
  duration_ms: number;
  error: string | null;
}

export interface WorkflowExecutionUndeclaredRow {
  step_key: string;
  step_id: string;
  tool: string;
  status: string;
  reason: string;
}

export interface WorkflowExecutionDiff {
  definition_id: string;
  version: number;
  state: string;
  checksum: string;
  task_id: string;
  task_type: string;
  task_status: string;
  totals: {
    definition_nodes: number;
    ran_steps: number;
    matched: number;
    not_executed: number;
    undeclared: number;
  };
  matched: WorkflowExecutionDiffRow[];
  not_executed: { key: string; kind: string; reason: string }[];
  undeclared: WorkflowExecutionUndeclaredRow[];
  unknown: string[];
}

/** A candidate a model proposed: validated by the server, saved only if the user accepts it. */
export interface WorkflowPlanCandidate {
  summary: string;
  graph: {
    nodes: (WorkflowNodeSpec & { rationale?: string })[];
    edges: WorkflowEdgeSpec[];
  };
  issues: WorkflowIssue[];
  valid: boolean;
  invocation_id: string | null;
  provider_note: string;
  planned_by: string;
}
