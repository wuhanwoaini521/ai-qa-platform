import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  GitPullRequest,
  Plus,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { CheckRun, PRChecksSummary, PRDiagnosisResponse, PullRequestInfo } from '../../../types';

interface PullRequestPanelProps {
  activePR: PullRequestInfo | null;
  prChecks: PRChecksSummary | null;
  loadingChecks: boolean;
  diagnosingCheckId: string | null;
  ciDiagnosisResult: PRDiagnosisResponse | null;
  onOpenPRModal: () => void;
  onRefreshChecks: () => void;
  onDiagnose: (check: CheckRun) => void;
  onDismissDiagnosis: () => void;
}

export const PullRequestPanel: React.FC<PullRequestPanelProps> = ({
  activePR,
  prChecks,
  loadingChecks,
  diagnosingCheckId,
  ciDiagnosisResult,
  onOpenPRModal,
  onRefreshChecks,
  onDiagnose,
  onDismissDiagnosis,
}) => {
  const { t } = useTranslation('studioPanels');

  return (
    <div style={{ padding: '8px' }}>
      {!activePR ? (
        <div style={{ textAlign: 'center', padding: '16px 8px' }}>
          <GitPullRequest size={32} color="var(--accent-green)" style={{ margin: '0 auto 10px' }} />
          <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink)', marginBottom: '6px' }}>
            {t('pullRequest.openTitle')}
          </h4>
          <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '12px' }}>
            {t('pullRequest.openDescription')}
          </p>
          <button
            className="btn btn-primary btn-sm"
            style={{ width: '100%', padding: '6px', background: 'var(--accent-green)', borderColor: 'var(--accent-green)' }}
            onClick={onOpenPRModal}
          >
            <Plus size={13} /> {t('pullRequest.create')}
          </button>
        </div>
      ) : (
        <div>
          {/* Active PR Header */}
          <div style={{ padding: '8px', background: 'var(--surface-inset)', borderRadius: 'var(--r-xs)', border: '1px solid var(--border-color)', marginBottom: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
              <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--accent-green)' }}>
                PR #{activePR.number}
              </span>
              <span
                style={{
                  fontSize: '10px',
                  padding: '2px 6px',
                  borderRadius: 'var(--r-md)',
                  background:
                    prChecks?.overall_status === 'PASSED'
                      ? 'var(--accent-green-soft)'
                      : prChecks?.overall_status === 'FAILED'
                      ? 'var(--accent-red-soft)'
                      : 'var(--accent-amber-soft)',
                  color:
                    prChecks?.overall_status === 'PASSED'
                      ? 'var(--accent-green)'
                      : prChecks?.overall_status === 'FAILED'
                      ? 'var(--accent-red)'
                      : 'var(--accent-amber)',
                  fontWeight: 700,
                }}
              >
                {prChecks?.overall_status || 'OPEN'}
              </span>
            </div>
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ink)', marginBottom: '6px' }}>
              {activePR.title}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '10px', color: 'var(--ink-muted)' }}>
                <code>{activePR.head_branch}</code> → <code>{activePR.base_branch}</code>
              </span>
              <a
                href={activePR.html_url}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: '11px', color: 'var(--accent-blue)', display: 'flex', alignItems: 'center', gap: '3px', textDecoration: 'none' }}
              >
                {t('pullRequest.openGithub')} <ExternalLink size={10} />
              </a>
            </div>
          </div>

          {/* GitHub Actions Checks */}
          <div style={{ marginBottom: '10px' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ink-muted)', marginBottom: '6px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>{t('pullRequest.checksTitle')}</span>
              <button
                className="icon-btn"
                title={t('pullRequest.refreshChecks')}
                disabled={loadingChecks}
                onClick={onRefreshChecks}
              >
                <RefreshCw size={11} className={loadingChecks ? 'spin' : ''} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {prChecks?.checks.map((check) => (
                <div
                  key={check.id}
                  style={{
                    padding: '6px 8px',
                    borderRadius: 'var(--r-xs)',
                    background: 'var(--surface-raised)',
                    border: '1px solid var(--line-strong)',
                    fontSize: '11px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      {check.status === 'PASSED' && <CheckCircle2 size={12} color="var(--accent-green)" />}
                      {check.status === 'FAILED' && <AlertCircle size={12} color="var(--accent-red)" />}
                      {check.status === 'RUNNING' && <RefreshCw size={12} color="var(--accent-amber)" className="spin" />}
                      {check.status === 'QUEUED' && <AlertTriangle size={12} color="var(--ink-muted)" />}
                      <span style={{ fontWeight: 600, color: 'var(--ink-soft)' }}>{check.name}</span>
                    </div>
                    <span style={{ fontSize: '9px', fontWeight: 700, color: check.status === 'PASSED' ? 'var(--accent-green)' : check.status === 'FAILED' ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                      {check.status}
                    </span>
                  </div>

                  {check.status === 'FAILED' && (
                    <div style={{ marginTop: '4px', borderTop: '1px dashed var(--line)', paddingTop: '4px' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ padding: '2px 6px', fontSize: '10px', gap: '3px' }}
                        disabled={diagnosingCheckId === check.id}
                        onClick={() => onDiagnose(check)}
                      >
                        <Sparkles size={10} color="var(--accent-violet)" /> {diagnosingCheckId === check.id ? t('pullRequest.diagnosing') : t('pullRequest.diagnose')}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* AI CI Diagnosis Result Modal/Box */}
          {ciDiagnosisResult && (
            <div style={{ padding: '8px', background: 'var(--accent-red-soft)', border: '1px solid var(--accent-red)', borderRadius: 'var(--r-xs)', fontSize: '11px', marginTop: '10px' }}>
              <div style={{ fontWeight: 700, color: 'var(--accent-red)', marginBottom: '4px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span>{t('pullRequest.diagnosisTitle', { classification: ciDiagnosisResult.classification })}</span>
                <button
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent-red)' }}
                  onClick={onDismissDiagnosis}
                >
                  ✕
                </button>
              </div>
              <div style={{ color: 'var(--accent-red)', marginBottom: '4px' }}>{ciDiagnosisResult.summary}</div>
              <div style={{ fontSize: '10px', color: 'var(--accent-amber)', background: 'var(--accent-amber-soft)', padding: '4px', borderRadius: 'var(--r-xs)' }}>
                <strong>{t('pullRequest.suggestedFix')}</strong> {ciDiagnosisResult.suggested_fix}
              </div>
            </div>
          )}

          <div style={{ marginTop: '12px' }}>
            <button
              className="btn btn-secondary btn-sm"
              style={{ width: '100%', padding: '4px', fontSize: '11px' }}
              onClick={onOpenPRModal}
            >
              <Plus size={12} /> {t('pullRequest.createAnother')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
