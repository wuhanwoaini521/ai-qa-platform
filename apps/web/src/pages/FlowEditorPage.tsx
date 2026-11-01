import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ChevronDown, ChevronUp, Play, Plus, Save, Trash2 } from 'lucide-react';
import { api } from '../api/client';
import { Project } from '../types';
import {
  FlowBranch,
  FlowDoc,
  FlowKind,
  FlowNode,
  KIND_LABEL,
  LocatorKind,
  countNodes,
  emptyFlow,
  emptyNode,
  flowFromScenario,
  slugTestName,
  toggleCriterion,
  insertNode,
  moveNode,
  removeNode,
  updateNode,
  validateFlow,
} from '../features/flow-canvas/flowDoc';

interface CompileAssertion {
  node_id: string;
  criterion_ids: string[];
  statement: string;
  check: string;
}

interface CompileResult {
  code: string;
  test_name: string;
  node_count: number;
  step_count: number;
  assertions: CompileAssertion[];
  warnings: string[];
}

const PALETTE: FlowKind[] = ['navigate', 'click', 'fill', 'assert_text', 'assert_visible', 'wait', 'condition'];
const LOCATOR_KINDS: LocatorKind[] = ['css', 'test_id', 'role', 'label', 'placeholder', 'id', 'name', 'text'];

export const FlowEditorPage: React.FC = () => {
  const { t } = useTranslation('flowEditor');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get('projectId') ?? '';
  const requirementId = searchParams.get('requirementId') ?? '';
  const scenarioId = searchParams.get('scenarioId') ?? '';

  const [project, setProject] = useState<Project | null>(null);
  const [flow, setFlow] = useState<FlowDoc>(() => emptyFlow('flow_canvas_case'));
  const [selected, setSelected] = useState<string | null>(null);
  const [compile, setCompile] = useState<CompileResult | null>(null);
  const [compileError, setCompileError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [seeded, setSeeded] = useState(false);
  const [criteria, setCriteria] = useState<{ id: string; description: string }[]>([]);
  const [requirementTitle, setRequirementTitle] = useState('');
  const [boundCaseId, setBoundCaseId] = useState<string | null>(null);
  const [bindingMessage, setBindingMessage] = useState('');
  const dragFrom = useRef<{ parentId: string | null; branch: FlowBranch; index: number } | null>(null);

  const validation = useMemo(() => validateFlow(flow), [flow]);
  const filePath = `tests/${flow.test_name}.py`;
  const nodeid = `${filePath}::${flow.test_name}`;

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    void api.getProject(projectId).then((item) => {
      if (alive) setProject(item);
    });
    return () => {
      alive = false;
    };
  }, [projectId]);

  // Seed from the requirement scenario when the editor is opened from the read-only canvas.
  useEffect(() => {
    if (seeded || !requirementId) return;
    let alive = true;
    void api.getRequirement(requirementId).then((requirement) => {
      if (!alive) return;
      const scenarios = (requirement.qa_model?.analysis?.scenarios ?? []) as unknown as {
        id: string;
        title: string;
        actions: string[];
        expected_outcomes: string[];
      }[];
      const scenario = scenarios.find((item) => item.id === scenarioId) ?? scenarios[0];
      setCriteria(
        ((requirement.qa_model?.criteria ?? []) as unknown as { id: string; description: string }[]).map((item) => ({
          id: item.id,
          description: item.description,
        })),
      );
      setRequirementTitle(requirement.title);
      const startUrl = project?.sut_base_url ?? '';
      if (scenario) {
        const seededFlow = flowFromScenario(scenario, startUrl);
        seededFlow.test_name = slugTestName(scenario.id);
        setFlow(seededFlow);
      } else {
        setFlow(emptyFlow('flow_canvas_case', startUrl));
      }
      setSeeded(true);
    });
    return () => {
      alive = false;
    };
  }, [project?.sut_base_url, requirementId, scenarioId, seeded]);

  useEffect(() => {
    if (validation.errors.length > 0) {
      setCompile(null);
      setCompileError('');
      return;
    }
    const timer = window.setTimeout(() => {
      void api
        .compileFlow(flow as unknown as Record<string, unknown>)
        .then((result) => {
          setCompile(result as CompileResult);
          setCompileError('');
        })
        .catch((reason) => {
          setCompile(null);
          setCompileError(String(reason));
        });
    }, 400);
    return () => window.clearTimeout(timer);
  }, [flow, validation.errors.length]);

  const rootNodes = flow.nodes;
  const activeNode = useMemo(() => {
    const find = (nodes: FlowNode[]): FlowNode | null => {
      for (const node of nodes) {
        if (node.id === selected) return node;
        const nested = find(node.then) ?? find(node.else_nodes);
        if (nested) return nested;
      }
      return null;
    };
    return find(flow.nodes);
  }, [flow.nodes, selected]);

  const addNode = (kind: FlowKind) => {
    const node = emptyNode(kind);
    const location = selected ? findLocation(flow, selected) : null;
    if (location) {
      const list = listFor(flow, location.parentId, location.branch);
      const index = list.findIndex((item) => item.id === selected);
      setFlow(insertNode(flow, location.parentId, location.branch, node, index + 1));
    } else {
      setFlow(insertNode(flow, null, 'then', node));
    }
    setSelected(node.id);
  };

  const move = (parentId: string | null, branch: FlowBranch, from: number, to: number) => {
    setFlow(moveNode(flow, parentId, branch, from, to));
  };

  const save = async () => {
    if (!projectId || !compile) return;
    setSaving(true);
    setSaveMessage('');
    try {
      await api.writeWorkspaceFile(projectId, filePath, compile.code);
      setSaveMessage(t('saved', { path: filePath }));
      if (requirementId && compile.assertions.length > 0) {
        const assertions = compile.assertions.flatMap((item) =>
          item.criterion_ids.map((criterionId) => ({
            criterion_id: criterionId,
            statement: item.statement,
            check: item.check,
          })),
        );
        const bound = await api.bindFlowCase({
          project_id: projectId,
          requirement_id: requirementId,
          scenario_id: scenarioId || null,
          file_path: filePath,
          test_name: flow.test_name,
          title: requirementTitle || flow.test_name,
          steps: flow.nodes.map((node) => node.description || node.kind).filter(Boolean),
          assertions,
        });
        setBoundCaseId(bound.case_id);
        setBindingMessage(t('boundCase', { id: bound.case_id }));
      } else if (requirementId) {
        setBindingMessage(t('noAssertionsToBind'));
      }
    } catch (reason) {
      setSaveMessage(t('saveFailed', { reason: String(reason) }));
    } finally {
      setSaving(false);
    }
  };

  const run = async () => {
    if (!projectId || !compile) return;
    setStarting(true);
    try {
      const created = await api.createTestRun({
        project_id: projectId,
        workspace_id: projectId,
        nodeids: [nodeid],
        requirement_id: requirementId || null,
        environment: { AI_QA_BROWSER_CHANNEL: 'chrome' },
      });
      setRunId(created.id);
      navigate(`/runs/${created.id}`);
    } catch (reason) {
      setSaveMessage(t('runFailed', { reason: String(reason) }));
    } finally {
      setStarting(false);
    }
  };

  const renderList = (nodes: FlowNode[], parentId: string | null, branch: FlowBranch) => (
    <ol className="flow-editor-list">
      {nodes.map((node, index) => (
        <li key={node.id}>
          <FlowCard
            node={node}
            selected={node.id === selected}
            onSelect={() => setSelected(node.id)}
            onMoveUp={() => move(parentId, branch, index, index - 1)}
            onMoveDown={() => move(parentId, branch, index, index + 1)}
            onDelete={() => {
              setFlow(removeNode(flow, node.id));
              if (selected === node.id) setSelected(null);
            }}
            onDragStart={() => {
              dragFrom.current = { parentId, branch, index };
            }}
            onDrop={() => {
              const from = dragFrom.current;
              if (from && from.parentId === parentId && from.branch === branch) {
                move(parentId, branch, from.index, index);
              }
              dragFrom.current = null;
            }}
          />
          {node.kind === 'condition' && (
            <div className="flow-editor-branches">
              {(['then', 'else_nodes'] as FlowBranch[]).map((side) => (
                <section key={side} className="flow-editor-branch">
                  <header>
                    <span>{side === 'then' ? t('branchThen') : t('branchElse')}</span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        const child = emptyNode('click');
                        setFlow(insertNode(flow, node.id, side, child));
                        setSelected(child.id);
                      }}
                    >
                      <Plus size={12} aria-hidden="true" />
                      {t('addStep')}
                    </button>
                  </header>
                  {renderList(node[side], node.id, side)}
                </section>
              ))}
            </div>
          )}
        </li>
      ))}
    </ol>
  );

  return (
    <div className="page-container flow-editor-page">
      <header className="page-header flow-page-header">
        <div>
          <span className="workspace-eyebrow">{t('eyebrow')}</span>
          <h2>{t('title')}</h2>
          <p className="subtitle">{t('subtitle')}</p>
        </div>
        <nav className="flow-page-actions" aria-label={t('actions')}>
          {requirementId && (
            <Link className="btn btn-secondary btn-sm" to={`/flows?projectId=${projectId}&requirementId=${requirementId}&scenarioId=${scenarioId}`}>
              <ArrowLeft size={14} aria-hidden="true" />
              {t('viewOnly')}
            </Link>
          )}
          <button className="btn btn-secondary btn-sm" type="button" onClick={save} disabled={saving || !compile}>
            <Save size={14} aria-hidden="true" />
            {saving ? t('saving') : t('save')}
          </button>
          <button className="btn btn-primary btn-sm" type="button" onClick={run} disabled={starting || !compile}>
            <Play size={14} aria-hidden="true" />
            {starting ? t('starting') : t('run')}
          </button>
        </nav>
      </header>

      <section className="card flow-editor-meta">
        <label className="flow-editor-field">
          <span>{t('testName')}</span>
          <input
            className="form-input"
            value={flow.test_name}
            onChange={(event) => setFlow({ ...flow, test_name: event.target.value.replace(/[^A-Za-z0-9_]/g, '_') })}
          />
        </label>
        <span className="flow-canvas-chip">{t('nodeCount', { count: countNodes(flow.nodes) })}</span>
        <span className="flow-canvas-chip">{filePath}</span>
        {project?.sut_base_url && <span className="flow-canvas-chip is-muted">{project.sut_base_url}</span>}
        {runId && <span className="flow-canvas-chip">{t('runStarted', { id: runId })}</span>}
      </section>

      {(validation.errors.length > 0 || validation.warnings.length > 0) && (
        <section className="flow-editor-messages" role="status">
          {validation.errors.map((code) => (
            <p key={code} className="flow-editor-error">{translateCode(t, code, 'error')}</p>
          ))}
          {validation.warnings.map((code) => (
            <p key={code} className="flow-editor-warning">{translateCode(t, code, 'warn')}</p>
          ))}
        </section>
      )}

      <div className="flow-editor-layout">
        <aside className="card flow-editor-palette">
          <h3>{t('palette')}</h3>
          {PALETTE.map((kind) => (
            <button key={kind} type="button" className="flow-editor-palette-item" onClick={() => addNode(kind)}>
              <Plus size={13} aria-hidden="true" />
              {t(KIND_LABEL[kind])}
            </button>
          ))}
          <p className="flow-editor-hint">{selected ? t('insertAfterSelected') : t('appendToEnd')}</p>
        </aside>

        <main className="card flow-editor-canvas">
          <h3>{t('canvasTitle')}</h3>
          {renderList(rootNodes, null, 'then')}
        </main>

        <aside className="card flow-editor-inspector">
          <h3>{t('inspector')}</h3>
          {activeNode ? (
            <NodeInspector
              node={activeNode}
              criteria={criteria}
              onChange={(patch) => setFlow(updateNode(flow, activeNode.id, patch))}
              onToggleCriterion={(criterionId) => setFlow(updateNode(flow, activeNode.id, { criterion_ids: toggleCriterion(activeNode, criterionId).criterion_ids }))}
            />
          ) : (
            <p className="flow-editor-hint">{t('selectNode')}</p>
          )}
        </aside>
      </div>

      <section className="card flow-editor-preview">
        <header className="flow-editor-preview-head">
          <h3>{t('preview')}</h3>
          {compile && (
            <span className="flow-canvas-chip">
              {t('previewStats', { nodes: compile.node_count, steps: compile.step_count })}
            </span>
          )}
        </header>
        {saveMessage && <p className="flow-editor-save-message">{saveMessage}</p>}
        {bindingMessage && <p className="flow-editor-save-message">{bindingMessage}</p>}
        {boundCaseId && (
          <p className="flow-editor-save-message">
            <a href={`/test-cases/${boundCaseId}`}>{t('openCase')}</a>
          </p>
        )}
        {compileError && <p className="flow-editor-error">{compileError}</p>}
        {compile ? <pre className="flow-editor-code">{compile.code}</pre> : <p className="flow-editor-hint">{t('previewPending')}</p>}
      </section>
    </div>
  );
};

const FlowCard: React.FC<{
  node: FlowNode;
  selected: boolean;
  onSelect: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
  onDragStart: () => void;
  onDrop: () => void;
}> = ({ node, selected, onSelect, onMoveUp, onMoveDown, onDelete, onDragStart, onDrop }) => {
  const { t } = useTranslation('flowEditor');
  const summary =
    node.kind === 'navigate'
      ? node.url
      : node.kind === 'condition'
        ? `${node.condition_kind}=${node.condition_value}`
        : node.kind === 'wait'
          ? `${node.value} ms`
          : `${node.locator_kind}=${node.locator_value}${node.value ? ` → ${node.value}` : ''}`;
  return (
    <article
      className={`flow-editor-node is-${node.kind}${selected ? ' is-selected' : ''}`}
      onClick={onSelect}
      draggable
      onDragStart={onDragStart}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        onDrop();
      }}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') onSelect();
      }}
    >
      <div className="flow-editor-node-main">
        <span className="flow-canvas-kind">{t(KIND_LABEL[node.kind])}</span>
        <strong>{node.description || summary || t('untitled')}</strong>
        {node.description && summary && <small>{summary}</small>}
      </div>
      <div className="flow-editor-node-actions">
        <button type="button" className="icon-btn" aria-label={t('moveUp')} onClick={(event) => { event.stopPropagation(); onMoveUp(); }}>
          <ChevronUp size={14} aria-hidden="true" />
        </button>
        <button type="button" className="icon-btn" aria-label={t('moveDown')} onClick={(event) => { event.stopPropagation(); onMoveDown(); }}>
          <ChevronDown size={14} aria-hidden="true" />
        </button>
        <button type="button" className="icon-btn" aria-label={t('delete')} onClick={(event) => { event.stopPropagation(); onDelete(); }}>
          <Trash2 size={14} aria-hidden="true" />
        </button>
      </div>
    </article>
  );
};

const NodeInspector: React.FC<{
  node: FlowNode;
  criteria: { id: string; description: string }[];
  onChange: (patch: Partial<FlowNode>) => void;
  onToggleCriterion: (criterionId: string) => void;
}> = ({ node, criteria, onChange, onToggleCriterion }) => {
  const { t } = useTranslation('flowEditor');
  return (
    <div className="flow-editor-inspector-body">
      <label className="flow-editor-field">
        <span>{t('description')}</span>
        <input className="form-input" value={node.description} onChange={(event) => onChange({ description: event.target.value })} />
      </label>
      {node.kind === 'navigate' && (
        <label className="flow-editor-field">
          <span>{t('url')}</span>
          <input className="form-input" value={node.url} onChange={(event) => onChange({ url: event.target.value })} />
        </label>
      )}
      {node.kind === 'condition' && (
        <>
          <label className="flow-editor-field">
            <span>{t('conditionKind')}</span>
            <select className="form-select" value={node.condition_kind} onChange={(event) => onChange({ condition_kind: event.target.value as FlowNode['condition_kind'] })}>
              <option value="css">CSS</option>
              <option value="text">{t('kindText')}</option>
              <option value="test_id">test id</option>
            </select>
          </label>
          <label className="flow-editor-field">
            <span>{t('conditionValue')}</span>
            <input className="form-input" value={node.condition_value} onChange={(event) => onChange({ condition_value: event.target.value })} />
          </label>
        </>
      )}
      {['click', 'fill', 'assert_text', 'assert_visible'].includes(node.kind) && (
        <>
          <label className="flow-editor-field">
            <span>{t('locatorKind')}</span>
            <select className="form-select" value={node.locator_kind} onChange={(event) => onChange({ locator_kind: event.target.value as LocatorKind })}>
              {LOCATOR_KINDS.map((kind) => (
                <option key={kind} value={kind}>{kind}</option>
              ))}
            </select>
          </label>
          <label className="flow-editor-field">
            <span>{t('locatorValue')}</span>
            <input className="form-input" value={node.locator_value} onChange={(event) => onChange({ locator_value: event.target.value })} />
          </label>
          {node.locator_kind === 'role' && (
            <label className="flow-editor-field">
              <span>{t('accessibleName')}</span>
              <input className="form-input" value={node.locator_name} onChange={(event) => onChange({ locator_name: event.target.value })} />
            </label>
          )}
        </>
      )}
      {(node.kind === 'fill' || node.kind === 'assert_text') && !node.env_var && (
        <label className="flow-editor-field">
          <span>{node.kind === 'fill' ? t('value') : t('expectedText')}</span>
          <input className="form-input" value={node.value} onChange={(event) => onChange({ value: event.target.value })} />
        </label>
      )}
      {node.kind === 'fill' && (
        <label className="flow-editor-field">
          <span>{t('envVar')}</span>
          <input
            className="form-input"
            placeholder="QA_DATA_EMAIL"
            value={node.env_var}
            onChange={(event) => onChange({ env_var: event.target.value.toUpperCase() })}
          />
        </label>
      )}
      {(node.kind === 'assert_text' || node.kind === 'assert_visible') && (
        <div className="flow-editor-criteria">
          <span>{t('criterionBinding')}</span>
          {criteria.length === 0 && <p className="flow-editor-hint">{t('noCriteria')}</p>}
          {criteria.map((criterion) => (
            <label key={criterion.id} className="flow-editor-criterion">
              <input
                type="checkbox"
                checked={node.criterion_ids.includes(criterion.id)}
                onChange={() => onToggleCriterion(criterion.id)}
              />
              <span>
                <strong>{criterion.id}</strong> {criterion.description}
              </span>
            </label>
          ))}
        </div>
      )}
      {node.kind === 'wait' && (
        <label className="flow-editor-field">
          <span>{t('waitMs')}</span>
          <input className="form-input" type="number" min={0} max={120000} value={node.value} onChange={(event) => onChange({ value: event.target.value })} />
        </label>
      )}
    </div>
  );
};

function translateCode(t: (key: string, options?: Record<string, unknown>) => string, code: string, _tone: 'error' | 'warn'): string {
  const [key, label] = code.split('|');
  if (!label) return t(key);
  const kindLabel = KIND_LABEL[label as FlowKind];
  return t(key, { label: kindLabel ? t(kindLabel) : label });
}

function listFor(flow: FlowDoc, parentId: string | null, branch: FlowBranch): FlowNode[] {
  if (parentId === null) return flow.nodes;
  const find = (nodes: FlowNode[]): FlowNode[] | null => {
    for (const node of nodes) {
      if (node.id === parentId) return node[branch];
      const nested = find(node.then) ?? find(node.else_nodes);
      if (nested) return nested;
    }
    return null;
  };
  return find(flow.nodes) ?? flow.nodes;
}

function findLocation(flow: FlowDoc, id: string) {
  const walk = (nodes: FlowNode[], parentId: string | null, branch: FlowBranch): { parentId: string | null; branch: FlowBranch } | null => {
    for (const node of nodes) {
      if (node.id === id) return { parentId, branch };
      const nested = walk(node.then, node.id, 'then') ?? walk(node.else_nodes, node.id, 'else_nodes');
      if (nested) return nested;
    }
    return null;
  };
  return walk(flow.nodes, null, 'then');
}
