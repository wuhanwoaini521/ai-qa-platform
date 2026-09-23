import React from 'react';
import { useTranslation } from 'react-i18next';
import { TestHistoryResponse } from '../../../types';

interface CaseExecutionHistoryPanelProps {
  caseHistory: TestHistoryResponse | null;
  loadingCaseHistory: boolean;
}

export const CaseExecutionHistoryPanel: React.FC<CaseExecutionHistoryPanelProps> = ({
  caseHistory,
  loadingCaseHistory,
}) => {
  const { t } = useTranslation('testCases');
  return (
    <div className="card">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="card-title">{t('historyTitle')}</span>
        </div>
        {caseHistory && (
          <span className="badge badge-ready" style={{ fontSize: '11px' }}>
            {t('historyStability', {
              classification: caseHistory.flaky_score.classification,
              score: caseHistory.flaky_score.score.toFixed(2),
            })}
          </span>
        )}
      </div>
      <div className="card-body">
        {loadingCaseHistory ? (
          <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
            {t('historyLoading')}
          </div>
        ) : caseHistory && caseHistory.executions.length > 0 ? (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '14px', textAlign: 'center' }}>
              <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '4px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{t('historyPassFail')}</div>
                <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px' }}>
                  <span style={{ color: '#16a34a' }}>{caseHistory.trend.pass_count}</span> /{' '}
                  <span style={{ color: '#dc2626' }}>{caseHistory.trend.fail_count}</span>
                </div>
              </div>
              <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '4px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{t('historyAvgDuration')}</div>
                <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px' }}>
                  {(caseHistory.trend.average_duration_ms / 1000).toFixed(2)}s
                </div>
              </div>
              <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '4px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{t('historyP95Duration')}</div>
                <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px' }}>
                  {(caseHistory.trend.p95_duration_ms / 1000).toFixed(2)}s
                </div>
              </div>
              <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '4px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{t('historyConfidence')}</div>
                <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px' }}>
                  {(caseHistory.flaky_score.confidence * 100).toFixed(0)}%
                </div>
              </div>
            </div>

            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
              {t('historyRecentExecutions')}
            </div>
            <table className="data-table" style={{ fontSize: '11px' }}>
              <thead>
                <tr>
                  <th style={{ padding: '6px 8px' }}>{t('common:status')}</th>
                  <th style={{ padding: '6px 8px' }}>{t('historyRunId')}</th>
                  <th style={{ padding: '6px 8px' }}>{t('common:duration')}</th>
                  <th style={{ padding: '6px 8px' }}>{t('historyRootCategory')}</th>
                  <th style={{ padding: '6px 8px' }}>{t('historyErrorDetails')}</th>
                </tr>
              </thead>
              <tbody>
                {caseHistory.executions.slice(0, 5).map((e) => (
                  <tr key={e.id}>
                    <td style={{ padding: '6px 8px' }}>
                      <span className={`badge badge-${e.status === 'PASSED' ? 'ready' : 'p0'}`}>
                        {e.status}
                      </span>
                    </td>
                    <td style={{ padding: '6px 8px', fontFamily: 'var(--font-mono)' }}>
                      #{e.run_id.slice(0, 8)}
                    </td>
                    <td style={{ padding: '6px 8px' }}>{(e.duration_ms / 1000).toFixed(2)}s</td>
                    <td style={{ padding: '6px 8px', color: 'var(--text-muted)' }}>
                      {e.failure_category || '—'}
                    </td>
                    <td style={{ padding: '6px 8px', color: e.error_message ? '#dc2626' : 'var(--text-muted)' }}>
                      {e.error_message ? e.error_message.slice(0, 60) + '...' : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
            {t('historyEmpty')}
          </div>
        )}
      </div>
    </div>
  );
};
