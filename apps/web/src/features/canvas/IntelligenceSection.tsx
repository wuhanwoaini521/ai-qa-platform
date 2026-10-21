import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { api } from '../../api/client';
import type {
  DiscoveryIntelligenceMetrics,
  DiscoverySuggestion,
  DiscoverySuggestionDetail,
  DiscoverySuggestionSummary,
} from '../../types/workflowCanvas';

/**
 * The model-assisted reading layer, shown inside the existing Discovery node detail.
 *
 * Everything here is advice: the rule verdict stays on the scenario, a rejected or ungrounded
 * reading is visible as such, and a case is only created by an explicit review decision.
 */
export function IntelligenceSection({
  runId,
  metrics,
}: {
  runId: string;
  metrics?: DiscoveryIntelligenceMetrics | null;
}) {
  const { t } = useTranslation('workspace');
  const [suggestions, setSuggestions] = useState<DiscoverySuggestion[]>([]);
  const [summary, setSummary] = useState<DiscoverySuggestionSummary | null>(null);
  const [detail, setDetail] = useState<DiscoverySuggestionDetail | null>(null);
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await api.listDiscoverySuggestions(runId);
      setSuggestions(next.suggestions);
      setSummary(next.summary);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const request = async (mode: 'analyze' | 'reanalyze', scenarioIds: string[] = []) => {
    setPending('request');
    try {
      const started = await api.requestDiscoveryIntelligence(runId, { mode, scenario_ids: scenarioIds });
      setNote(t(started.reused ? 'canvas.intelligence.reused' : 'canvas.intelligence.requested', { id: started.task_id }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending(null);
    }
  };

  const review = async (suggestionId: string, decision: string, caseIds: string[] = []) => {
    setPending(decision);
    try {
      const result = await api.reviewDiscoverySuggestion(runId, suggestionId, {
        decision,
        comment: reason,
        case_ids: caseIds,
      });
      setNote(
        result.created_case_id
          ? t('canvas.intelligence.caseCreated', { id: result.created_case_id })
          : t('canvas.intelligence.reviewed', { state: result.suggestion.review_status }),
      );
      setReason('');
      await load();
      if (detail?.suggestion_id === suggestionId) setDetail(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending(null);
    }
  };

  const openEvidence = async (suggestionId: string) => {
    setPending('evidence');
    try {
      setDetail(await api.getDiscoverySuggestion(runId, suggestionId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending(null);
    }
  };

  const counts = metrics ?? null;

  return (
    <section className="lw-evidence-block lw-intelligence">
      <h4>{t('canvas.intelligence.title')}</h4>
      <p className="lw-evidence-summary">
        {counts
          ? t('canvas.intelligence.counts', {
              total: counts.suggestions,
              pending: counts.pending_review,
              accepted: counts.accepted,
              rejected: counts.rejected,
            })
          : t('canvas.intelligence.none')}
        {' · '}
        {t('canvas.intelligence.jev', {
          graded: counts?.jev_graded ?? 0,
          fallback: counts?.jev_fallback ?? summary?.jev_fallback ?? 0,
        })}
      </p>
      <div className="lw-evidence-kinds">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={pending === 'request'}
          onClick={() => void request('analyze')}
        >
          {t('canvas.intelligence.request')}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>
          {t('canvas.intelligence.refresh')}
        </button>
      </div>
      {note && <p className="lw-evidence-note" role="status">{note}</p>}
      {suggestions.length === 0 && <p className="lw-evidence-empty">{t('canvas.intelligence.empty')}</p>}
      {suggestions.length > 0 && (
        <ul className="lw-evidence">
          {suggestions.map((suggestion) => (
            <li key={suggestion.suggestion_id}>
              <span>{suggestion.suggested_title || suggestion.scenario_title}</span>
              <small className={`is-${analysisTone(suggestion.analysis_status)}`}>
                {t(`canvas.intelligence.analysis.${suggestion.analysis_status}`)}
              </small>
              {suggestion.coverage_status && (
                <small>{t('canvas.intelligence.ruleVerdict', { state: suggestion.coverage_status })}</small>
              )}
              <small className={`is-${suggestion.jev.status === 'JEV_GRADED' ? 'ok' : 'attention'}`}>
                {t(`canvas.intelligence.jevStatus.${String(suggestion.jev.status ?? 'NOT_GRADED')}`)}
                {suggestion.grade ? ` · ${suggestion.grade}` : ''}
              </small>
              <small>{t('canvas.intelligence.reviewState', { state: suggestion.review_status })}</small>
              <small>{t('canvas.intelligence.citations', { count: suggestion.evidence_ids.length })}</small>
              <div className="lw-detail-actions">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={pending === 'evidence'}
                  onClick={() => void openEvidence(suggestion.suggestion_id)}
                >
                  {t('canvas.intelligence.viewEvidence')}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={pending === 'ACCEPT'}
                  onClick={() => void review(suggestion.suggestion_id, 'ACCEPT')}
                >
                  {t('canvas.intelligence.accept')}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={pending === 'REJECT'}
                  onClick={() => void review(suggestion.suggestion_id, 'REJECT')}
                >
                  {t('canvas.intelligence.reject')}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={pending === 'APPROVE_CREATE_CASE' || !suggestion.suggested_title}
                  onClick={() => void review(suggestion.suggestion_id, 'APPROVE_CREATE_CASE')}
                >
                  {t('canvas.intelligence.approveCase')}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={pending === 'request'}
                  onClick={() => void request('reanalyze', [suggestion.scenario_id])}
                >
                  {t('canvas.intelligence.reanalyze')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <label className="lw-evidence-note">
        {t('canvas.intelligence.reason')}
        <input
          type="text"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          aria-label={t('canvas.intelligence.reason')}
        />
      </label>
      {detail && (
        <>
          <h5>{t('canvas.intelligence.evidenceTitle')}</h5>
          <p className="lw-evidence-note">{detail.reasoning || detail.summary || detail.reason}</p>
          <ul className="lw-evidence">
            {detail.evidence.map((row) => (
              <li key={row.evidence_id}>
                <code>{row.evidence_id}</code>
                <small>{row.kind}</small>
                {row.artifact_id && <small>{t('canvas.evidenceUi.artifact', { id: row.artifact_id.slice(0, 8) })}</small>}
              </li>
            ))}
            {detail.evidence.length === 0 && <li className="lw-evidence-empty">{t('canvas.intelligence.noCitation')}</li>}
          </ul>
          {detail.related_cases.length > 0 && (
            <ul className="lw-evidence">
              {detail.related_cases.map((entry) => (
                <li key={entry.id}>
                  <span>{entry.title}</span>
                  {entry.file_path && <code>{entry.file_path}</code>}
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => void review(detail.suggestion_id, 'LINK', detail.related_cases.map((item) => item.id))}
                  >
                    {t('canvas.intelligence.linkCases')}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {error && <p className="lw-evidence-note" role="alert">{error}</p>}
    </section>
  );
}

function analysisTone(status: string): string {
  if (status === 'COMPLETED') return 'ok';
  if (status === 'REJECTED' || status === 'FAILED') return 'bad';
  return 'attention';
}
