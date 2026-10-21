/**
 * Editing mode for a QA workflow definition.
 *
 * This is authoring only: it writes a draft, publishes an immutable version, and never starts a task.
 * The server validates and stores; the runtime is reached only through the published version.
 */
import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import { api } from '../../api/client';
import type { AgentTask } from '../../types';
import type {
  WorkflowCatalogueEntry,
  WorkflowDefinitionDetail,
  WorkflowDefinitionList,
  WorkflowExecutionDiff,
  WorkflowPlanCandidate,
  WorkflowIssue,
  WorkflowVersionComparison,
} from '../../types/workflowDefinition';
import {
  addNode,
  applyEdit,
  sameLayout,
  autoLayout,
  connect,
  describeInput,
  disconnect,
  emptyEditor,
  issueTone,
  localIssues,
  parseInput,
  redo,
  removeNode,
  riskLabel,
  sameGraph,
  setInput,
  undo,
  updateNode,
  type EditorError,
  type EditorHistory,
  type EditorState,
} from './workflowEditorModel';
import { treeStateLabel } from './executionTreeModel';
import './workflow-editor.css';

interface EditorNodeData extends Record<string, unknown> {
  label: string;
  kind: string;
  risk: ReturnType<typeof riskLabel>;
  selected: boolean;
}

function EditorNode({ data }: NodeProps<Node<EditorNodeData>>) {
  return (
    <div className={`wfe-node is-${data.risk}${data.selected ? ' is-selected' : ''}`} data-node-key={data.label}>
      <Handle type="target" position={Position.Left} />
      <span className="wfe-node-key">{data.label}</span>
      <span className="wfe-node-title">{data.kind}</span>
      <span className={`wfe-node-risk is-${data.risk}`}>{data.risk}</span>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { editor: EditorNode };

const ERROR_TEXT: Record<EditorError, string> = {
  self_link: 'workflowEditor.errors.selfLink',
  duplicate_link: 'workflowEditor.errors.duplicateLink',
  cycle: 'workflowEditor.errors.cycle',
  unknown_kind: 'workflowEditor.errors.unknownKind',
  missing_node: 'workflowEditor.errors.missingNode',
};

function EditorSurface({
  state,
  catalogue,
  selectedKey,
  onSelect,
  onConnect,
  onDeleteEdge,
  onDeleteNodes,
  onMove,
  onDragStart,
}: {
  state: EditorState;
  catalogue: WorkflowCatalogueEntry[];
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  onConnect: (connection: Connection) => void;
  onDeleteEdge: (edge: Edge) => void;
  onDeleteNodes: (keys: string[]) => void;
  onMove: (key: string, position: { x: number; y: number }) => void;
  onDragStart: () => void;
}) {
  const riskOf = (kind: string): WorkflowCatalogueEntry['risk'] =>
    catalogue.find((entry) => entry.kind === kind)?.risk ?? 'READ';
  const flownodes = useMemo<Node<EditorNodeData>[]>(
    () =>
      state.nodes.map((node, index) => ({
        id: node.key,
        type: 'editor',
        position: node.position ?? { x: 40 + index * 24, y: 40 + index * 24 },
        data: {
          label: node.key,
          kind: node.kind,
          risk: riskLabel(riskOf(node.kind)),
          selected: node.key === selectedKey,
        },
        initialWidth: 236,
        initialHeight: 78,
      })),
    [state.nodes, selectedKey, catalogue],
  );
  const flowEdges = useMemo<Edge[]>(
    () =>
      state.edges.map((edge) => ({
        id: `${edge.source}->${edge.target}`,
        source: edge.source,
        target: edge.target,
        type: 'smoothstep',
        animated: false,
      })),
    [state.edges],
  );
  return (
    <ReactFlow
      nodes={flownodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      onConnect={onConnect}
      onEdgesDelete={(edges) => {
        for (const edge of edges) {
          onDeleteEdge(edge);
        }
      }}
      onNodeClick={(_, node) => onSelect(node.id)}
      onNodeDragStart={onDragStart}
      onNodeDragStop={(_, node) => onMove(node.id, node.position)}
      onPaneClick={() => onSelect(null)}
      onNodesDelete={(nodes) => onDeleteNodes(nodes.map((node) => node.id))}
      fitView
      fitViewOptions={{ padding: 0.12, maxZoom: 0.95 }}
      minZoom={0.2}
      nodesConnectable
      proOptions={{ hideAttribution: false }}
    >
      <Background gap={22} />
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable />
    </ReactFlow>
  );
}

export function WorkflowEditorPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation('workspace');
  const [list, setList] = useState<WorkflowDefinitionList | null>(null);
  const [detail, setDetail] = useState<WorkflowDefinitionDetail | null>(null);
  const [history, setHistory] = useState<EditorHistory>(emptyEditor());
  const [issues, setIssues] = useState<WorkflowIssue[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [canPublish, setCanPublish] = useState(false);
  const [compare, setCompare] = useState<WorkflowVersionComparison | null>(null);
  const [newName, setNewName] = useState('');
  const [tasks, setTasks] = useState<AgentTask[] | null>(null);
  const [diffTaskId, setDiffTaskId] = useState('');
  const [diff, setDiff] = useState<WorkflowExecutionDiff | null>(null);
  const [planPrompt, setPlanPrompt] = useState('');
  const [plan, setPlan] = useState<WorkflowPlanCandidate | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const dragStart = useRef<EditorState | null>(null);
  // A slow initial load must not overwrite a definition the user already picked or created.
  const loadSeq = useRef(0);

  const catalogue = detail?.catalogue ?? list?.catalogue ?? [];
  const savedState = useMemo<EditorState>(
    () => ({
      nodes: (detail?.draft.graph.nodes ?? []).map((node) => ({ ...node, inputs: { ...(node.inputs ?? {}) } })),
      edges: (detail?.draft.graph.edges ?? []).map((edge) => ({ source: edge.source, target: edge.target })),
    }),
    [detail],
  );
  // A dragged card is a real change to save, even though it is not part of the graph's meaning.
  const dirty = !sameGraph(history.present, savedState) || !sameLayout(history.present, savedState);

  const load = useCallback(
    async (definitionId?: string) => {
      const seq = loadSeq.current + 1;
      loadSeq.current = seq;
      const listing = await api.getWorkflows(projectId);
      if (seq !== loadSeq.current) return;
      setList(listing);
      const target = definitionId ?? listing.definitions[listing.definitions.length - 1]?.id ?? '';
      if (!target) {
        setDetail(null);
        setHistory(emptyEditor());
        return;
      }
      const loaded = await api.getWorkflow(target);
      if (seq !== loadSeq.current) return;
      setDetail(loaded);
      setHistory(emptyEditor(loaded.draft.graph));
      setIssues(loaded.draft.issues ?? []);
      setSelectedKey(null);
      setCompare(null);
    },
    [projectId],
  );

  useEffect(() => {
    void load().catch((error: Error) => setMessage(error.message));
  }, [load]);

  useEffect(() => {
    api
      .getCurrentUserProfile()
      .then((profile) => setCanPublish(profile.permissions.includes('project:write')))
      .catch(() => setCanPublish(false));
  }, []);

  const edit = useCallback((next: EditorState) => setHistory((current) => applyEdit(current, next)), []);

  const onConnect = useCallback(
    (connection: Connection) => {
      const result = connect(history.present, connection.source, connection.target);
      if ('error' in result) {
        setMessage(t(ERROR_TEXT[result.error]));
        return;
      }
      setMessage(null);
      edit(result.state);
    },
    [edit, history.present, t],
  );

  const selected = history.present.nodes.find((node) => node.key === selectedKey) ?? null;
  const selectedSpec = catalogue.find((entry) => entry.kind === selected?.kind) ?? null;

  const run = useCallback(
    async (action: () => Promise<void>) => {
      setBusy(true);
      try {
        await action();
      } catch (error) {
        setMessage((error as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const createWorkflow = () =>
    run(async () => {
      const name = newName.trim() || t('workflowEditor.defaultName');
      const created = await api.createWorkflow(projectId, { name });
      loadSeq.current += 1;
      setNewName('');
      setDetail(created);
      setHistory(emptyEditor(created.draft.graph));
      setIssues(created.draft.issues ?? []);
      setList(await api.getWorkflows(projectId));
      setMessage(t('workflowEditor.messages.created'));
    });

  const save = () =>
    run(async () => {
      if (!detail) {
        return;
      }
      const result = await api.saveWorkflowDraft(detail.id, history.present, detail.draft.checksum);
      setIssues(result.issues);
      setMessage(
        result.issues.length ? t('workflowEditor.messages.savedWithIssues', { count: result.issues.length }) : t('workflowEditor.messages.saved'),
      );
      const refreshed = await api.getWorkflow(detail.id);
      setDetail(refreshed);
      setHistory((current) => ({ ...current, present: current.present }));
    });

  const validate = () =>
    run(async () => {
      if (!detail) {
        return;
      }
      const result = await api.validateWorkflow(detail.id, history.present);
      setIssues(result.issues);
      setMessage(
        result.issues.length ? t('workflowEditor.messages.issuesFound', { count: result.issues.length }) : t('workflowEditor.messages.valid'),
      );
    });

  const publish = () =>
    run(async () => {
      if (!detail) {
        return;
      }
      if (dirty) {
        setMessage(t('workflowEditor.messages.saveFirst'));
        return;
      }
      const result = await api.publishWorkflow(detail.id);
      setMessage(t('workflowEditor.messages.published', { version: result.published.version }));
      await load(detail.id);
    });

  const restore = (version: number) =>
    run(async () => {
      if (!detail) {
        return;
      }
      const result = await api.restoreWorkflowVersion(detail.id, version);
      await load(detail.id);
      setIssues(result.issues);
      setMessage(t('workflowEditor.messages.restored', { version }));
    });

  const openDiff = () =>
    run(async () => {
      if (!tasks) {
        setTasks(await api.getTasks(projectId));
      }
    });

  const loadDiff = () =>
    run(async () => {
      if (!detail || !diffTaskId) {
        return;
      }
      setDiff(await api.getWorkflowExecutionDiff(detail.id, diffTaskId, detail.published ? null : detail.draft.version));
    });

  const askForPlan = async () => {
    if (!planPrompt.trim()) {
      return;
    }
    setPlanning(true);
    setPlanError(null);
    try {
      setPlan(await api.planWorkflow(projectId, planPrompt.trim()));
    } catch (error) {
      setPlan(null);
      setPlanError((error as Error).message);
    } finally {
      setPlanning(false);
    }
  };

  /** A candidate only reaches the canvas when the user puts it there; saving stays a separate act. */
  const applyPlan = () => {
    if (!plan) {
      return;
    }
    edit({
      nodes: plan.graph.nodes.map((node) => ({ ...node, inputs: { ...(node.inputs ?? {}) } })),
      edges: plan.graph.edges.map((edge) => ({ source: edge.source, target: edge.target })),
    });
    setSelectedKey(null);
    setMessage(t('workflowEditor.planApplied'));
  };

  const compareVersions = (base: number, head: number) =>
    run(async () => {
      if (!detail) {
        return;
      }
      setCompare(await api.compareWorkflowVersions(detail.id, base, head));
    });

  return (
    <div className="wfe-panel">
      <header className="wfe-toolbar">
        <select
          aria-label={t('workflowEditor.definition')}
          value={detail?.id ?? ''}
          onChange={(event) => void run(async () => load(event.target.value))}
        >
          <option value="">{t('workflowEditor.none')}</option>
          {(list?.definitions ?? []).map((definition) => (
            <option key={definition.id} value={definition.id}>
              {definition.name}
            </option>
          ))}
        </select>
        <input
          aria-label={t('workflowEditor.newName')}
          placeholder={t('workflowEditor.newName')}
          value={newName}
          onChange={(event) => setNewName(event.target.value)}
          className="wfe-name"
        />
        <button type="button" onClick={() => void createWorkflow()} disabled={busy}>
          {t('workflowEditor.create')}
        </button>
        <span className="wfe-separator" />
        <button type="button" onClick={() => setHistory(undo)} disabled={!history.past.length}>
          {t('workflowEditor.undo')}
        </button>
        <button type="button" onClick={() => setHistory(redo)} disabled={!history.future.length}>
          {t('workflowEditor.redo')}
        </button>
        <button type="button" onClick={() => edit(autoLayout(history.present))} disabled={!detail}>
          {t('workflowEditor.autoLayout')}
        </button>
        <button type="button" onClick={() => void validate()} disabled={!detail || busy}>
          {t('workflowEditor.validate')}
        </button>
        <button type="button" onClick={() => void save()} disabled={!detail || busy || !dirty} className="wfe-primary">
          {dirty ? t('workflowEditor.saveDraft') : t('workflowEditor.saved')}
        </button>
        <button
          type="button"
          onClick={() => void publish()}
          disabled={!detail || busy || dirty || !canPublish || issues.length > 0}
          title={canPublish ? undefined : t('workflowEditor.needLead')}
        >
          {t('workflowEditor.publish')}
        </button>
      </header>

      {message && (
        <p className="wfe-message" role="status">
          {message}
        </p>
      )}

      {detail && (
        <details className="wfe-diff" onToggle={() => void openDiff()}>
          <summary>{t('workflowEditor.executionDiff')}</summary>
          <div className="wfe-diff-body">
            <select
              aria-label={t('workflowEditor.task')}
              value={diffTaskId}
              onChange={(event) => setDiffTaskId(event.target.value)}
            >
              <option value="">{t('workflowEditor.pickTask')}</option>
              {(tasks ?? []).map((task) => (
                <option key={task.id} value={task.id}>
                  {t(`executionTree.taskTypes.${task.type}`, { defaultValue: task.type })} · {t(`executionTree.states.${treeStateLabel(task.status)}`, { defaultValue: task.status })} · {task.id.slice(0, 8)}
                </option>
              ))}
            </select>
            <button type="button" onClick={() => void loadDiff()} disabled={!diffTaskId || busy}>
              {t('workflowEditor.compareWithRun')}
            </button>
            {diff && (
              <div className="wfe-diff-result">
                <p className="wfe-muted">
                  {t('workflowEditor.diffTotals', {
                    matched: diff.totals.matched,
                    nodes: diff.totals.definition_nodes,
                    steps: diff.totals.ran_steps,
                    undeclared: diff.totals.undeclared,
                  })}
                </p>
                <ul className="wfe-diff-list">
                  {diff.matched.map((row) => (
                    <li key={`m-${row.key}`} className="is-ok">
                      = {row.key} · {row.kind} → {row.step_key} · {row.status} · {Math.round(row.duration_ms)}ms
                    </li>
                  ))}
                  {diff.not_executed.map((row) => (
                    <li key={`n-${row.key}`} className="is-attention">
                      ? {row.key} · {row.kind} · {row.reason}
                    </li>
                  ))}
                  {diff.undeclared.map((row) => (
                    <li key={`u-${row.step_id}`} className="is-bad">
                      + {row.step_key} · {row.tool} · {row.reason}
                    </li>
                  ))}
                </ul>
                <p className="wfe-muted">{t('workflowEditor.diffUnknown', { fields: diff.unknown.join(', ') })}</p>
              </div>
            )}
          </div>
        </details>
      )}

      {detail && (
        <details className="wfe-plan">
          <summary>{t('workflowEditor.planTitle')}</summary>
          <div className="wfe-plan-body">
            <p className="wfe-muted">{t('workflowEditor.planHint')}</p>
            <textarea
              aria-label={t('workflowEditor.planTitle')}
              value={planPrompt}
              placeholder={t('workflowEditor.planPlaceholder')}
              rows={2}
              maxLength={2000}
              onChange={(event) => setPlanPrompt(event.target.value)}
            />
            <button type="button" onClick={() => void askForPlan()} disabled={planning || !planPrompt.trim()}>
              {planning ? t('workflowEditor.planGenerating') : t('workflowEditor.planGenerate')}
            </button>
            {planError && (
              <p className="wfe-message is-bad" role="alert">
                {planError}
              </p>
            )}
            {plan && (
              <div className="wfe-plan-result">
                <p className="wfe-plan-summary">{plan.summary}</p>
                <p className={plan.valid ? 'wfe-ok' : 'wfe-bad'} role="status">
                  {plan.valid ? t('workflowEditor.planValid') : t('workflowEditor.planInvalid')}
                </p>
                <ol className="wfe-plan-nodes">
                  {plan.graph.nodes.map((node) => (
                    <li key={node.key}>
                      <strong>{node.key}</strong> · {node.kind}
                      {node.rationale && <span className="wfe-muted"> — {node.rationale}</span>}
                    </li>
                  ))}
                </ol>
                {plan.issues.length > 0 && (
                  <ul className="wfe-issues">
                    {plan.issues.map((issue) => (
                      <li key={`${issue.code}-${issue.node_key ?? ''}`} className="is-bad">
                        {issue.code} · {issue.message}
                      </li>
                    ))}
                  </ul>
                )}
                <button type="button" onClick={applyPlan} disabled={plan.graph.nodes.length === 0}>
                  {t('workflowEditor.planApply')}
                </button>
              </div>
            )}
          </div>
        </details>
      )}

      {!detail ? (
        <div className="wfe-empty">
          <h3>{t('workflowEditor.emptyTitle')}</h3>
          <p>{t('workflowEditor.emptyHint')}</p>
        </div>
      ) : (
        <div className="wfe-body">
          <aside className="wfe-palette" aria-label={t('workflowEditor.palette')}>
            <h4>{t('workflowEditor.palette')}</h4>
            {catalogue.map((entry) => (
              <button
                key={entry.kind}
                type="button"
                className={`wfe-palette-item is-${riskLabel(entry.risk)}`}
                onClick={() => {
                  const result = addNode(history.present, catalogue, entry.kind);
                  if ('error' in result) {
                    setMessage(t(ERROR_TEXT[result.error]));
                    return;
                  }
                  edit(result.state);
                  setSelectedKey(result.key);
                }}
                title={entry.summary}
              >
                <span>{t(`workflowEditor.kinds.${entry.kind}`, { defaultValue: entry.title })}</span>
                <small>{riskLabel(entry.risk)}</small>
              </button>
            ))}
            <h4>{t('workflowEditor.versions')}</h4>
            <ul className="wfe-versions">
              {detail.versions.map((version) => (
                <li key={version.id}>
                  <span>
                    v{version.version} · {version.state === 'PUBLISHED' ? t('workflowEditor.published') : t('workflowEditor.draft')}
                  </span>
                  <small>
                    {version.node_count} {t('workflowEditor.nodes')}
                  </small>
                  <span className="wfe-version-actions">
                    {version.state === 'PUBLISHED' && (
                      <button type="button" onClick={() => void restore(version.version)} disabled={busy}>
                        {t('workflowEditor.restore')}
                      </button>
                    )}
                    {detail.published && detail.draft.version && version.version !== detail.draft.version && (
                      <button
                        type="button"
                        onClick={() => void compareVersions(version.version, detail.draft.version as number)}
                        disabled={busy}
                      >
                        {t('workflowEditor.compare')}
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </aside>

          <div className="wfe-canvas">
            <ReactFlowProvider>
              <EditorSurface
                state={history.present}
                catalogue={catalogue}
                selectedKey={selectedKey}
                onSelect={setSelectedKey}
                onConnect={onConnect}
                onDeleteEdge={(edge) => edit(disconnect(history.present, edge.source, edge.target))}
                onDeleteNodes={(keys) => {
                  let next = history.present;
                  for (const key of keys) {
                    next = removeNode(next, key);
                  }
                  edit(next);
                  setSelectedKey(null);
                }}
                onMove={(key, position) => {
                  const before = dragStart.current;
                  dragStart.current = null;
                  setHistory((current) => ({
                    past: before ? [...current.past, before].slice(-80) : current.past,
                    present: updateNode(current.present, key, { position }),
                    future: [],
                  }));
                }}
                onDragStart={() => {
                  dragStart.current = history.present;
                }}
              />
            </ReactFlowProvider>
          </div>

          <aside className="wfe-inspector" aria-label={t('workflowEditor.inspector')}>
            {selected && selectedSpec ? (
              <>
                <h4>{selected.key}</h4>
                <p className="wfe-inspector-kind">{selected.kind}</p>
                <label>
                  {t('workflowEditor.title')}
                  <input
                    value={selected.title ?? ''}
                    onChange={(event) => edit(updateNode(history.present, selected.key, { title: event.target.value }))}
                  />
                </label>
                {selectedSpec.inputs.map((input) => (
                  <label key={input.name}>
                    {input.name}
                    {input.required && <span className="wfe-required">*</span>}
                    <input
                      value={describeInput((selected.inputs ?? {})[input.name])}
                      placeholder={input.kind === 'list' ? 'a, b' : '$input.name'}
                      onChange={(event) =>
                        edit(setInput(history.present, selected.key, input.name, parseInput(event.target.value, input.kind)))
                      }
                    />
                    <small>{input.description}</small>
                  </label>
                ))}
                {selectedSpec.inputs.length === 0 && <p className="wfe-muted">{t('workflowEditor.noInputs')}</p>}
                <button
                  type="button"
                  className="wfe-danger"
                  onClick={() => {
                    edit(removeNode(history.present, selected.key));
                    setSelectedKey(null);
                  }}
                >
                  {t('workflowEditor.deleteNode')}
                </button>
              </>
            ) : (
              <p className="wfe-muted">{t('workflowEditor.selectNode')}</p>
            )}

            <h4>{t('workflowEditor.issues')}</h4>
            {issues.length === 0 ? (
              <p className="wfe-muted">{t('workflowEditor.noIssues')}</p>
            ) : (
              <ul className="wfe-issues">
                {issues.map((issue) => (
                  <li key={`${issue.code}-${issue.node_key ?? 'graph'}`} className={`is-${issueTone(issue.code)}`}>
                    <button type="button" onClick={() => issue.node_key && setSelectedKey(issue.node_key)}>
                      <strong>{issue.code}</strong>
                      <span>{issue.message}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {localIssues(history.present, catalogue).length > 0 && issues.length === 0 && (
              <p className="wfe-muted">
                {t('workflowEditor.unsavedIssues', { count: localIssues(history.present, catalogue).length })}
              </p>
            )}
          </aside>
        </div>
      )}

      {compare && (
        <div className="wfe-compare" role="dialog" aria-label={t('workflowEditor.compareTitle')}>
          <header>
            <h4>
              {t('workflowEditor.compareTitle')} v{compare.base.version} → v{compare.head.version}
            </h4>
            <button type="button" onClick={() => setCompare(null)}>
              {t('workflowEditor.close')}
            </button>
          </header>
          {compare.diff.identical ? (
            <p className="wfe-muted">{t('workflowEditor.identical')}</p>
          ) : (
            <ul>
              {compare.diff.nodes.added.map((node) => (
                <li key={`add-${node.key}`} className="is-ok">
                  + {node.key} · {node.kind}
                </li>
              ))}
              {compare.diff.nodes.removed.map((node) => (
                <li key={`del-${node.key}`} className="is-bad">
                  − {node.key} · {node.kind}
                </li>
              ))}
              {compare.diff.nodes.changed.map((node) => (
                <li key={`chg-${node.key}`} className="is-attention">
                  ~ {node.key} · {node.fields.join(', ')}
                </li>
              ))}
              {compare.diff.edges.added.map((edge) => (
                <li key={`ea-${edge.source}-${edge.target}`} className="is-ok">
                  + {edge.source} → {edge.target}
                </li>
              ))}
              {compare.diff.edges.removed.map((edge) => (
                <li key={`er-${edge.source}-${edge.target}`} className="is-bad">
                  − {edge.source} → {edge.target}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

