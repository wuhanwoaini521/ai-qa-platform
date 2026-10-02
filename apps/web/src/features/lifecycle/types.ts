export interface CoverageRefs { criterion_ids: string[]; rule_ids: string[]; risk_ids: string[]; flow_ids: string[] }
export interface Scenario {
  domain?: 'UI' | 'API' | 'Python' | 'Domain';
  id: string; title: string; intent: string; priority: string; path_type: string; technique: string;
  coverage: CoverageRefs; actions: string[]; expected_outcomes: string[]; rationale: string;
}
export interface AnalysisRecord {
  analysis_snapshot?: RequirementDocument['analysis'];
  id: string; status: string; provider: string; model: string; input_hash: string; prompt_version: string;
  started_at: string; finished_at?: string; error_code?: string; error?: string;
  stages: {id: string; title: string; status: string; summary: string; source: string; duration_ms: number}[];
  decisions: {choice: string | null; provider: string; model?: string; reason?: string; fallback_used: boolean; name: string}[];
}
export interface RequirementDocument {
  display_id: string; criteria: {id: string; description: string; negative_required: boolean}[];
  rules: {id: string; description: string; criterion_ids: string[]}[]; constraints: string[]; dependencies: string[];
  analysis?: {
    summary: string; actors: string[]; entities: string[]; assumptions: string[]; dependencies: string[];
    ambiguities: {id: string; question: string; impact: string}[];
    business_flow: {id: string; title: string; summary: string; next_ids: string[]; criterion_ids: string[]}[];
    risks: {id: string; title: string; severity: string; probability: string; impact: string; criterion_ids: string[]; rationale: string}[];
    scenarios: Scenario[]; coverage_gaps: string[];
  } | null;
  history: AnalysisRecord[];
}
export interface ModernTestModel {
  display_id: string; intent: string; scenario_id?: string; coverage: CoverageRefs; path_type: string; technique: string;
  data: Record<string, unknown>; oracles: {kind: string; description: string; criterion_ids: string[]}[]; evidence: string[]; missing: string[];
}
export interface KnowledgeNode {id: string; kind: string; label: string; summary: string; href: string; status: string; metadata: Record<string, unknown>}
export interface KnowledgeEdge {source: string; target: string; relation: string}
export interface CoverageMetric {
  key: string; label: string; covered: number; total: number; percentage: number | null;
  items: {id: string; label: string; summary?: string; covered: boolean; case_ids?: string[]; automated_case_ids?: string[]; executed_case_ids?: string[]; passed_case_ids?: string[]; run_id?: string}[];
}
export interface ProjectKnowledge {
  project_id: string; nodes: KnowledgeNode[]; edges: KnowledgeEdge[]; coverage: CoverageMetric[];
  gaps: {id: string; kind: string; label: string; summary: string; reason: string; requirement_id: string}[];
  counts: Record<string, number>; truncated: boolean;
}
