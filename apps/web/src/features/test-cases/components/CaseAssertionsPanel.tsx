import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../../../api/client';

interface CaseAssertion {
  id: string;
  criterion_id: string;
  statement: string;
  nodeid?: string;
  state: string;
  run?: { run_id: string; execution_status: string; finished_at: string | null } | null;
}

const STATE_LABEL: Record<string, string> = {
  PASSED: 'statePassed',
  FAILED: 'stateFailed',
  SKIPPED: 'stateSkipped',
  CANCELLED: 'stateCancelled',
  ERROR: 'stateError',
  NEVER_RUN: 'stateNeverRun',
  UNBOUND: 'stateUnbound',
};

export const CaseAssertionsPanel: React.FC<{ caseId: string }> = ({ caseId }) => {
  const { t } = useTranslation('testCases');
  const [assertions, setAssertions] = useState<CaseAssertion[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    setAssertions(null);
    setError('');
    void api
      .getCaseAssertions(caseId)
      .then((result) => {
        if (alive) setAssertions(result.assertions);
      })
      .catch((reason) => {
        if (alive) setError(String(reason));
      });
    return () => {
      alive = false;
    };
  }, [caseId]);

  if (error) return null;
  if (!assertions || assertions.length === 0) return null;

  return (
    <section className="case-assertions" aria-label={t('assertionsTitle')}>
      <div className="case-assertions-heading">
        <strong>{t('assertionsTitle')}</strong>
        <span>{t('assertionsCount', { count: assertions.length })}</span>
      </div>
      <ul>
        {assertions.map((assertion) => (
          <li key={assertion.id} className="case-assertion-row">
            <code>{assertion.criterion_id}</code>
            <span className="case-assertion-statement">{assertion.statement}</span>
            <small className={`ds-tag badge badge-run is-${assertion.state.toLowerCase().replace('_', '-')}`}>
              {t(STATE_LABEL[assertion.state] ?? 'stateUnbound')}
            </small>
            {assertion.run && (
              <a className="lc-run-link" href={`/runs/${assertion.run.run_id}?caseId=${caseId}`}>
                {t('viewRunResult')}
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
};
