/** Mirrors `packages/project-model/project_model/execution_trace.py`. */
export type TraceNodeType = 'task' | 'step' | 'invocation' | 'evidence' | 'artifact' | 'run' | 'suggestion';

export type TraceEdgeType = 'CHILD_OF' | 'INVOKES' | 'PRODUCES' | 'DEPENDS_ON';

export interface TraceTokenUsage {
  input_tokens: number | null;
  output_tokens: number | null;
  source: string;
}

export interface TraceNode {
  id: string;
  type: TraceNodeType;
  label: string;
  subtitle: string | null;
  status: string | null;
  task_id: string | null;
  step_id: string | null;
  invocation_id: string | null;
  parent_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  provider: string | null;
  model: string | null;
  token_usage: TraceTokenUsage | null;
  cost: number | null;
  pricing: string;
  evidence_ids: string[];
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  links: Record<string, string>;
  unknown: string[];
  fallback_used: boolean | null;
}

export interface TraceEdge {
  id: string;
  source: string;
  target: string;
  type: TraceEdgeType;
}

export interface ExecutionTrace {
  project_id: string | null;
  generated_at: string;
  root_task_id: string | null;
  root_count: number;
  status: string | null;
  workflow_execution_id?: string | null;
  workflow_definition_id?: string | null;
  workflow_version_id?: string | null;
  workflow_version?: number | null;
  workflow_checksum?: string | null;
  nodes: TraceNode[];
  edges: TraceEdge[];
  counts: Record<TraceNodeType, number>;
  unknown: string[];
}
