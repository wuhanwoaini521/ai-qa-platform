import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowDown, ArrowLeft, ArrowUp, LayoutDashboard, Pencil, Play, Plus, Save, Trash2, Workflow } from 'lucide-react';
import { api } from '../api/client';
import { Project, Requirement, TestDesign } from '../types';
import { FlowCanvas } from '../features/flow-canvas/FlowCanvas';
import { FlowEditorPage } from './FlowEditorPage';
import type { ScenarioLike } from '../features/flow-canvas/flowGraph';
import { buildWorkspaceHref } from '../app/workspaceContext';

export const FlowCanvasPage: React.FC = () => {
  const { t } = useTranslation('flowCanvas');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedMode = searchParams.get('mode');
  const mode = requestedMode === 'edit' || requestedMode === 'plan' ? requestedMode : 'view';
  const projectId = searchParams.get('projectId') ?? '';
  const requirementId = searchParams.get('requirementId') ?? '';
  const scenarioId = searchParams.get('scenarioId') ?? '';
  const [project, setProject] = useState<Project | null>(null);
  const [requirement, setRequirement] = useState<Requirement | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [designs, setDesigns] = useState<TestDesign[]>([]);
  const [scenarioDraft, setScenarioDraft] = useState<ScenarioLike | null>(null);
  const [savingPlan, setSavingPlan] = useState(false);
  const [startingExplore, setStartingExplore] = useState(false);
  const [planMessage, setPlanMessage] = useState('');
  const [planError, setPlanError] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    const request = requirementId
      ? api.getRequirement(requirementId)
      : Promise.reject(new Error(t('missingRequirement')));
    void request
      .then(async (item) => {
        if (!alive) return;
        setRequirement(item);
        const loadedDesigns = await api.getTestDesigns(item.id).catch(() => []);
        if (alive) setDesigns(loadedDesigns);
        const owner = projectId || item.project_id;
        if (owner) {
          try {
            const loaded = await api.getProject(owner);
            if (alive) setProject(loaded);
          } catch {
            /* project metadata is optional for the canvas */
          }
        }
      })
      .catch((reason) => {
        if (alive) setError(String(reason));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [projectId, requirementId, t]);

  const document = requirement?.qa_model ?? null;
  const scenarios: ScenarioLike[] = useMemo(
    () => (document?.analysis?.scenarios ?? []) as unknown as ScenarioLike[],
    [document],
  );
  const activeScenario = scenarios.find((item) => item.id === scenarioId) ?? scenarios[0] ?? null;
  const activeDesign = designs.find((item) => item.scenario_model?.id === activeScenario?.id) ?? null;
  const displayScenario = mode === 'plan' && scenarioDraft?.id === activeScenario?.id ? scenarioDraft : activeScenario;
  const normalizedActions = scenarioDraft?.actions.map((item) => item.trim()).filter(Boolean) ?? [];
  const normalizedOutcomes = scenarioDraft?.expected_outcomes.map((item) => item.trim()).filter(Boolean) ?? [];
  const planSaved = Boolean(
    activeDesign?.scenario_model && scenarioDraft
    && JSON.stringify(normalizedActions) === JSON.stringify(activeDesign.scenario_model.actions)
    && JSON.stringify(normalizedOutcomes) === JSON.stringify(activeDesign.scenario_model.expected_outcomes),
  );
  const criteria = (document?.criteria ?? []).map((item) => ({ id: item.id, description: item.description }));

  useEffect(() => {
    if (!activeScenario) {
      setScenarioDraft(null);
      return;
    }
    const persisted = activeDesign?.scenario_model;
    setScenarioDraft({
      ...activeScenario,
      ...(persisted ?? {}),
      actions: [...(persisted?.actions ?? activeScenario.actions)],
      expected_outcomes: [...(persisted?.expected_outcomes ?? activeScenario.expected_outcomes)],
    });
    setPlanMessage('');
    setPlanError('');
  }, [activeScenario?.id, activeDesign?.id, activeDesign?.updated_at]);

  const switchMode = (next: 'view' | 'plan' | 'edit') => {
    setSearchParams(
      (current) => {
        const params = new URLSearchParams(current);
        if (next === 'view') params.delete('mode');
        else params.set('mode', next);
        return params;
      },
      { replace: true },
    );
  };

  const updatePlanItem = (key: 'actions' | 'expected_outcomes', index: number, value: string) => {
    setScenarioDraft((current) => current ? { ...current, [key]: current[key].map((item, itemIndex) => itemIndex === index ? value : item) } : current);
    setPlanMessage('');
  };

  const movePlanItem = (key: 'actions' | 'expected_outcomes', index: number, offset: number) => {
    setScenarioDraft((current) => {
      if (!current) return current;
      const items = [...current[key]];
      const target = index + offset;
      if (target < 0 || target >= items.length) return current;
      [items[index], items[target]] = [items[target], items[index]];
      return { ...current, [key]: items };
    });
    setPlanMessage('');
  };

  const savePlan = async () => {
    if (!requirement || !activeScenario || !scenarioDraft) return;
    const actions = scenarioDraft.actions.map((item) => item.trim()).filter(Boolean);
    if (actions.length === 0 || actions.length > 24) {
      setPlanError(t('planActionLimit'));
      return;
    }
    const outcomes = scenarioDraft.expected_outcomes.map((item) => item.trim()).filter(Boolean);
    if (outcomes.length > 20) {
      setPlanError(t('planOutcomeLimit'));
      return;
    }
    setSavingPlan(true);
    setPlanError('');
    setPlanMessage('');
    try {
      let target = activeDesign;
      if (!target) {
        const adopted = await api.adoptLifecycleDesigns(requirement.id);
        setDesigns(adopted);
        target = adopted.find((item) => item.scenario_model?.id === activeScenario.id) ?? null;
      }
      if (!target) throw new Error(t('planSaveFailed'));
      const saved = await api.updateTestDesign(target.id, {
        scenario_model: {
          ...scenarioDraft,
          actions,
          expected_outcomes: outcomes,
        } as TestDesign['scenario_model'],
      });
      setDesigns((current) => [...current.filter((item) => item.id !== saved.id), saved]);
      setScenarioDraft({ ...scenarioDraft, actions, expected_outcomes: outcomes });
      setPlanMessage(t('planSaved'));
    } catch (reason) {
      setPlanError(`${t('planSaveFailed')}：${String(reason)}`);
    } finally {
      setSavingPlan(false);
    }
  };

  const startGuidedExplore = async () => {
    if (!project || !requirement || !scenarioDraft || !activeDesign || !project.sut_base_url) return;
    setStartingExplore(true);
    setPlanError('');
    let recorderSessionId: string | null = null;
    try {
      const session = await api.createRecorderSession(project.id, project.sut_base_url, []);
      recorderSessionId = session.id;
      if (session.navigation_error) throw new Error(String(session.navigation_error));
      const created = await api.createTask({
        type: 'EXPLORE_PAGE',
        goal: `${scenarioDraft.title}：按已确认的流程节点逐步探索网页，并为每个节点保留页面证据。`,
        project_id: project.id,
        workspace_id: project.id,
        max_ai_calls: 50,
        inputs: {
          url: project.sut_base_url,
          recorder_session_id: session.id,
          max_actions_per_guided_step: 4,
          strategy: 'agent',
          guided_plan: {
            design_id: activeDesign.id,
            scenario_id: scenarioDraft.id,
            title: scenarioDraft.title,
            steps: scenarioDraft.actions.map((action, index) => ({ id: `step-${index + 1}`, title: action.trim().slice(0, 120) || `${t('actionLabel')} ${index + 1}`, action })),
            expected_outcomes: scenarioDraft.expected_outcomes,
          },
        },
      });
      const href = buildWorkspaceHref({ projectId: project.id, requirementId: requirement.id, testDesignId: activeDesign.id, taskId: created.id, view: 'browser' });
      navigate(`${href}${href.includes('?') ? '&' : '?'}session_id=${encodeURIComponent(session.id)}&panel=runtime`);
    } catch (reason) {
      if (recorderSessionId) await api.closeRecorderSession(recorderSessionId).catch(() => undefined);
      setPlanError(`${t('exploreStartFailed')}：${String(reason)}`);
    } finally {
      setStartingExplore(false);
    }
  };

  const selectScenario = (nextId: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set('scenarioId', nextId);
        return next;
      },
      { replace: true },
    );
  };

  const backHref = requirement
    ? `/workspace/${encodeURIComponent(requirement.project_id)}?projectId=${encodeURIComponent(requirement.project_id)}&requirementId=${encodeURIComponent(requirement.id)}&stage=requirement&tab=design`
    : '/workspace';

  return (
    <div className="page-container flow-page">
      <header className="page-header flow-page-header">
        <div>
          <span className="workspace-eyebrow">{t('eyebrow')}</span>
          <h2>{t('title')}</h2>
            <p className="subtitle">{mode === 'edit' ? t('subtitleEdit') : mode === 'plan' ? t('subtitlePlan') : t('subtitle')}</p>
        </div>
        <nav className="flow-page-actions" aria-label={t('actions')}>
          <Link className="ds-btn ds-btn-sm btn btn-secondary btn-sm" to={backHref}>
            <ArrowLeft size={14} aria-hidden="true" />
            {t('backToRequirement')}
          </Link>
          <div className="flow-view-tabs" role="tablist" aria-label={t('viewSwitch')}>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'view'}
              className={`ds-btn flow-view-tab${mode === 'view' ? ' is-active' : ''}`}
              onClick={() => switchMode('view')}
            >
              <LayoutDashboard size={13} aria-hidden="true" />
              {t('tabView')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'plan'}
              className={`ds-btn flow-view-tab${mode === 'plan' ? ' is-active' : ''}`}
              onClick={() => switchMode('plan')}
              disabled={!requirement}
            >
              <Workflow size={13} aria-hidden="true" />
              {t('tabPlan')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'edit'}
              className={`ds-btn flow-view-tab${mode === 'edit' ? ' is-active' : ''}`}
              onClick={() => switchMode('edit')}
              disabled={!requirement}
            >
              <Pencil size={13} aria-hidden="true" />
              {t('tabEdit')}
            </button>
          </div>
        </nav>
      </header>

      {loading && <div className="ds-card card page-empty-state" role="status">{t('loading')}</div>}
      {!loading && error && <div className="ds-card card page-empty-state" role="alert">{t('loadFailed')}</div>}
      {!loading && !error && (!document || scenarios.length === 0) && (
        <div className="ds-card card page-empty-state">
          <Workflow size={28} aria-hidden="true" />
          <h4>{t('emptyTitle')}</h4>
          <p>{t('emptyHint')}</p>
        </div>
      )}

      {!loading && !error && document && mode === 'edit' && requirement && (
        <FlowEditorPage embedded />
      )}

      {!loading && !error && document && activeScenario && mode !== 'edit' && (
        <>
          <section className="ds-card card flow-page-toolbar">
            <div className="flow-page-title">
              <strong>{requirement?.title ?? ''}</strong>
              <small>{t('requirementMeta', { count: scenarios.length })}</small>
            </div>
            <label className="flow-page-select">
              <span>{t('scenarioLabel')}</span>
              <select
                className="ds-select form-select"
                value={activeScenario.id}
                onChange={(event) => selectScenario(event.target.value)}
              >
                {scenarios.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.id} · {scenario.title}
                  </option>
                ))}
              </select>
            </label>
          </section>
          {mode === 'plan' && scenarioDraft && (
            <section className="ds-card card flow-plan-editor" aria-label={t('planEditorLabel')}>
              <header className="flow-plan-editor-heading">
                <div><strong>{t('planTitle')}</strong><p>{t('planDescription')}</p></div>
                <div className="flow-plan-actions">
                  <button type="button" className="ds-btn ds-btn-sm btn btn-secondary btn-sm" onClick={() => void savePlan()} disabled={savingPlan || startingExplore}>
                    <Save size={14} aria-hidden="true" />{savingPlan ? t('planSaving') : t('planSave')}
                  </button>
                  <button type="button" className="ds-btn ds-btn-sm btn btn-primary btn-sm" onClick={() => void startGuidedExplore()} disabled={savingPlan || startingExplore || !planSaved || !project?.sut_base_url}>
                    <Play size={14} aria-hidden="true" />{startingExplore ? t('exploreStarting') : t('exploreByPlan')}
                  </button>
                </div>
              </header>
              {!planSaved && <p className="flow-plan-note">{t('planNeedsSave')}</p>}
              {!project?.sut_base_url && <p className="flow-plan-note">{t('missingSutUrl')}</p>}
              {planMessage && <p className="flow-plan-message" role="status">{planMessage}</p>}
              {planError && <p className="flow-plan-error" role="alert">{planError}</p>}
              <PlanList
                title={t('actionsTitle')}
                items={scenarioDraft.actions}
                onChange={(index, value) => updatePlanItem('actions', index, value)}
                onMove={(index, offset) => movePlanItem('actions', index, offset)}
                onAdd={() => setScenarioDraft((current) => current ? { ...current, actions: [...current.actions, ''] } : current)}
                onRemove={(index) => setScenarioDraft((current) => current ? { ...current, actions: current.actions.filter((_, itemIndex) => itemIndex !== index) } : current)}
              />
              <PlanList
                title={t('outcomesTitle')}
                items={scenarioDraft.expected_outcomes}
                onChange={(index, value) => updatePlanItem('expected_outcomes', index, value)}
                onMove={(index, offset) => movePlanItem('expected_outcomes', index, offset)}
                onAdd={() => setScenarioDraft((current) => current ? { ...current, expected_outcomes: [...current.expected_outcomes, ''] } : current)}
                onRemove={(index) => setScenarioDraft((current) => current ? { ...current, expected_outcomes: current.expected_outcomes.filter((_, itemIndex) => itemIndex !== index) } : current)}
              />
            </section>
          )}
          <FlowCanvas
            key={activeScenario.id}
            scenario={displayScenario ?? activeScenario}
            criteria={criteria}
            sutBaseUrl={project?.sut_base_url ?? null}
            planned={mode === 'plan'}
          />
        </>
      )}
    </div>
  );
};

const PlanList: React.FC<{
  title: string;
  items: string[];
  onChange: (index: number, value: string) => void;
  onMove: (index: number, offset: number) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}> = ({ title, items, onChange, onMove, onAdd, onRemove }) => {
  const { t } = useTranslation('flowCanvas');
  return (
    <section className="flow-plan-list">
      <div className="flow-plan-list-heading">
        <h3>{title}</h3>
        <button type="button" className="ds-btn ds-btn-sm btn btn-secondary btn-sm" onClick={onAdd}><Plus size={13} aria-hidden="true" />{t('planAdd')}</button>
      </div>
      <ol>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>
            <span className="flow-plan-list-index">{index + 1}</span>
            <input className="ds-input form-control" value={item} maxLength={500} aria-label={`${title} ${index + 1}`} onChange={(event) => onChange(index, event.target.value)} />
            <button type="button" className="ds-btn ds-btn-icon btn btn-secondary btn-sm" aria-label={t('moveUp')} disabled={index === 0} onClick={() => onMove(index, -1)}><ArrowUp size={14} aria-hidden="true" /></button>
            <button type="button" className="ds-btn ds-btn-icon btn btn-secondary btn-sm" aria-label={t('moveDown')} disabled={index === items.length - 1} onClick={() => onMove(index, 1)}><ArrowDown size={14} aria-hidden="true" /></button>
            <button type="button" className="ds-btn ds-btn-icon btn btn-secondary btn-sm" aria-label={t('removeStep')} onClick={() => onRemove(index)}><Trash2 size={14} aria-hidden="true" /></button>
          </li>
        ))}
      </ol>
    </section>
  );
};
