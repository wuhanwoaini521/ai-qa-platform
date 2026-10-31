import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Workflow } from 'lucide-react';
import { api } from '../api/client';
import { Project, Requirement } from '../types';
import { FlowCanvas } from '../features/flow-canvas/FlowCanvas';
import type { ScenarioLike } from '../features/flow-canvas/flowGraph';

export const FlowCanvasPage: React.FC = () => {
  const { t } = useTranslation('flowCanvas');
  const [searchParams, setSearchParams] = useSearchParams();
  const projectId = searchParams.get('projectId') ?? '';
  const requirementId = searchParams.get('requirementId') ?? '';
  const scenarioId = searchParams.get('scenarioId') ?? '';
  const [project, setProject] = useState<Project | null>(null);
  const [requirement, setRequirement] = useState<Requirement | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

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
  const criteria = (document?.criteria ?? []).map((item) => ({ id: item.id, description: item.description }));

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
          <p className="subtitle">{t('subtitle')}</p>
        </div>
        <nav className="flow-page-actions" aria-label={t('actions')}>
          <Link className="btn btn-secondary btn-sm" to={backHref}>
            <ArrowLeft size={14} aria-hidden="true" />
            {t('backToRequirement')}
          </Link>
        </nav>
      </header>

      {loading && <div className="card page-empty-state" role="status">{t('loading')}</div>}
      {!loading && error && <div className="card page-empty-state" role="alert">{t('loadFailed')}</div>}
      {!loading && !error && (!document || scenarios.length === 0) && (
        <div className="card page-empty-state">
          <Workflow size={28} aria-hidden="true" />
          <h4>{t('emptyTitle')}</h4>
          <p>{t('emptyHint')}</p>
        </div>
      )}

      {!loading && !error && document && activeScenario && (
        <>
          <section className="card flow-page-toolbar">
            <div className="flow-page-title">
              <strong>{requirement?.title ?? ''}</strong>
              <small>{t('requirementMeta', { count: scenarios.length })}</small>
            </div>
            <label className="flow-page-select">
              <span>{t('scenarioLabel')}</span>
              <select
                className="form-select"
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
          <FlowCanvas
            key={activeScenario.id}
            scenario={activeScenario}
            criteria={criteria}
            sutBaseUrl={project?.sut_base_url ?? null}
          />
        </>
      )}
    </div>
  );
};
