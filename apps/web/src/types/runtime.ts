export interface RuntimeSourceContext {
  nodeId?: string;
  testCaseId?: string;
  failureId?: string;
  taskId?: string;
  runId?: string;
}

export type RuntimeSourceOpener = (
  path: string,
  line: number,
  context?: RuntimeSourceContext,
) => void;

export interface RuntimeSpan {
  id: string;
  kind: string;
  title: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  task_id: string | null;
  test_run_id: string | null;
  step_id: string | null;
  timestamp_source?: string | null;
  operation?: string | null;
  provider?: string | null;
  model?: string | null;
}
export interface RuntimeStep extends RuntimeSpan {
  key: string;
  tool: string;
  dependencies: string[];
  retry_count: number;
  inputs_summary: string;
  outputs_summary: string;
  error: string | null;
  failure_type?: string | null;
  ai_provider?: string | null;
  ai_model?: string | null;
  validation_error?: string | null;
}
export interface RuntimeEvent {
  id: string;
  source: string;
  source_id: string;
  runtime_id: string;
  task_id: string | null;
  test_run_id: string | null;
  trace_run_id: string | null;
  step_id: string | null;
  timestamp: string | null;
  type: string;
  category: string;
  status: string | null;
  title: string;
  summary: string;
  duration_ms: number | null;
  metadata: Record<string, unknown>;
}
export interface RuntimeArtifact {
  id: string;
  artifact_id: string | null;
  name: string;
  type: string;
  source: string;
  step_id: string | null;
  test_run_id: string | null;
  case_id: string | null;
  created_at: string | null;
  size_bytes: number | null;
  content_type: string | null;
  url: string | null;
}
export interface RuntimeSnapshot {
  id: string;
  kind: 'task' | 'run';
  status: string;
  title: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  task:
    | (RuntimeSpan & {
        type: string;
        current_step_id: string | null;
        retry_count: number;
        failure_reason?: string | null;
        replan_count?: number;
        max_replans?: number;
        recorder_session_id?: string | null;
      })
    | null;
  blocking: {
    step_id: string | null;
    step_key: string | null;
    failure_type: string;
    reason: string;
    recoverable: boolean;
    recovery_actions: ('retry_step' | 'replan' | 'inspect_ai_output')[];
  } | null;
  steps: RuntimeStep[];
  runs: (RuntimeSpan & {
    relationship_source: string;
    parent_run_id: string | null;
    origin_failure_id: string | null;
    total: number;
    passed: number;
    failed: number;
    skipped: number;
  })[];
  executions: RuntimeSpan[];
  run_ancestors: RuntimeSnapshot['runs'];
  ai_invocations: RuntimeSpan[];
  decisions: {
    id: string;
    step_id: string | null;
    name: string;
    provider: string;
    selected: string;
    confidence: number | null;
    created_at: string | null;
  }[];
  evidence: {
    id: string;
    step_id: string | null;
    type: string;
    source: string;
    summary: string;
    artifact_id: string | null;
    created_at: string | null;
  }[];
  browser_sessions: (RuntimeSpan & {
    browser_session_id: string;
    current_url: string;
    case_execution_id: string | null;
  })[];
  failures: {
    id: string;
    test_run_id: string;
    execution_id: string;
    title: string;
    classification: string;
    message: string;
    created_at: string | null;
  }[];
  artifacts: RuntimeArtifact[];
  summary: {
    completed_steps: number;
    total_steps: number;
    active_step_ids: string[];
    next_step_ids: string[];
    failures: number;
    retries: number;
    ai_calls: number | null;
    artifacts: number;
    approval: boolean;
  };
  events: RuntimeEvent[];
  event_cursor: number;
  events_truncated: boolean;
}
