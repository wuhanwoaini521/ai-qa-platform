import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TestCase } from '../../types';
import { KnowledgeDrawer } from './KnowledgeDrawer';
import './lifecycle.css';

type CaseView = 'flow' | 'table' | 'data';

export function ModernCasePanel({ item }: { item: TestCase }) {
  const { t } = useTranslation('lifecycle');
  const dataHeadingId = useId();
  const [view, setView] = useState<CaseView>('flow');
  const [showKnowledge, setShowKnowledge] = useState(false);
  const model = item.test_model;

  if (!model) return null;

  const missing = [
    ...model.missing,
    ...(model.oracles.length === 0 ? [t('missingOracle')] : []),
    ...(Object.keys(model.data).length === 0 ? [t('missingData')] : []),
  ];

  return (
    <section className="lc-card lc-case-panel">
      <div className="lc-header">
        <div>
          <span className="lc-eyebrow">
            {model.display_id || item.id} · {model.technique}
          </span>
          <h3>{t('testIntent')}</h3>
          <p>{model.intent}</p>
        </div>
        <button
          className="btn btn-secondary"
          type="button"
          onClick={() => setShowKnowledge(true)}
        >
          {t('whyCase')}
        </button>
      </div>

      <div className="lc-chip-list">
        {Object.values(model.coverage).flat().map((id) => (
          <Link
            className="lc-chip"
            key={id}
            to={`/projects/${item.project_id}/requirements/${item.requirement_id}?tab=knowledge&node=${id}`}
          >
            {id}
          </Link>
        ))}
      </div>

      <div className="lc-tabs">
        <button
          className={view === 'flow' ? 'selected' : ''}
          type="button"
          aria-pressed={view === 'flow'}
          onClick={() => setView('flow')}
        >
          {t('flow')}
        </button>
        <button
          className={view === 'table' ? 'selected' : ''}
          type="button"
          aria-pressed={view === 'table'}
          onClick={() => setView('table')}
        >
          {t('table')}
        </button>
        <button
          className={view === 'data' ? 'selected' : ''}
          type="button"
          aria-pressed={view === 'data'}
          onClick={() => setView('data')}
        >
          {t('data')}
        </button>
      </div>

      {view === 'flow' && (
        <div className="lc-flow lc-case-flow">
          {item.steps.map((step, index) => (
            <div className="lc-flow-step" key={index}>
              <i>{index + 1}</i>
              <span>{step}</span>
            </div>
          ))}
          <div className="lc-notice">
            <strong>{t('oracles')}</strong>
            {model.oracles.map((oracle, index) => (
              <p key={index}>
                {oracle.kind} · {oracle.description}{' '}
                <small>{oracle.criterion_ids.join(', ')}</small>
              </p>
            ))}
          </div>
        </div>
      )}

      {view === 'table' && (
        <div className="lc-table-scroll lc-case-table-scroll">
          <table className="data-table lc-case-table" aria-label={t('table')}>
            <colgroup>
              <col className="lc-case-action-column" />
              <col />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">{t('actions')}</th>
                <th scope="col">{t('oracles')}</th>
              </tr>
            </thead>
            <tbody>
              {item.steps.map((step, index) => (
                <tr key={index}>
                  <td>{index + 1} · {step}</td>
                  <td>
                    {index === item.steps.length - 1
                      ? model.oracles.map((oracle) => oracle.description).join('；')
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {view === 'data' && (
        <section className="lc-case-data" aria-labelledby={dataHeadingId}>
          <h3 id={dataHeadingId}>{t('data')}</h3>
          <pre className="lc-json-viewer">
            <code>{JSON.stringify(model.data, null, 2)}</code>
          </pre>
          <p className="lc-caption">{t('dataSource')}</p>
        </section>
      )}

      <details
        className={`lc-readiness ${missing.length ? 'is-incomplete' : 'is-ready'}`}
        open={missing.length > 0}
      >
        <summary className="lc-readiness-summary">
          <span className="lc-readiness-title">{t('readiness')}</span>
          <span className="lc-readiness-status">
            {missing.length ? t('needsInput') : t('readyForDraft')}
          </span>
        </summary>
        <div className="lc-readiness-content">
          <p>{missing.length ? missing.join('；') : t('draftNotVerified')}</p>
          <p className="lc-caption">{t('evidence')} · {model.evidence.join(' · ')}</p>
          {item.binding && (
            <Link
              className="btn btn-primary"
              to={`/projects/${item.project_id}/studio/file/${item.binding.file_path}?caseId=${item.id}&target=${encodeURIComponent(item.binding.nodeid)}`}
            >
              {t('openAutomation')}
            </Link>
          )}
        </div>
      </details>

      {showKnowledge && (
        <KnowledgeDrawer
          projectId={item.project_id}
          entityId={item.id}
          onClose={() => setShowKnowledge(false)}
        />
      )}
    </section>
  );
}
