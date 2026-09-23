import React from 'react';
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
}) => (
  <div style={{ padding: '8px' }}>
    {!activePR ? (
      <div style={{ textAlign: 'center', padding: '16px 8px' }}>
        <GitPullRequest size={32} color="#059669" style={{ margin: '0 auto 10px' }} />
        <h4 style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a', marginBottom: '6px' }}>
          Open Pull Request
        </h4>
        <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '12px' }}>
          Connect your QA automation branch directly to GitHub PR workflow with automated validation checks.
        </p>
        <button
          className="btn btn-primary btn-sm"
          style={{ width: '100%', padding: '6px', background: '#059669', borderColor: '#059669' }}
          onClick={onOpenPRModal}
        >
          <Plus size={13} /> Create Pull Request
        </button>
      </div>
    ) : (
      <div>
        {/* Active PR Header */}
        <div style={{ padding: '8px', background: '#f8fafc', borderRadius: '6px', border: '1px solid var(--border-color)', marginBottom: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#059669' }}>
              PR #{activePR.number}
            </span>
            <span
              style={{
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '12px',
                background:
                  prChecks?.overall_status === 'PASSED'
                    ? '#dcfce7'
                    : prChecks?.overall_status === 'FAILED'
                    ? '#fee2e2'
                    : '#fef3c7',
                color:
                  prChecks?.overall_status === 'PASSED'
                    ? '#166534'
                    : prChecks?.overall_status === 'FAILED'
                    ? '#991b1b'
                    : '#92400e',
                fontWeight: 700,
              }}
            >
              {prChecks?.overall_status || 'OPEN'}
            </span>
          </div>
          <div style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
            {activePR.title}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '10px', color: '#64748b' }}>
              <code>{activePR.head_branch}</code> → <code>{activePR.base_branch}</code>
            </span>
            <a
              href={activePR.html_url}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: '11px', color: '#2563eb', display: 'flex', alignItems: 'center', gap: '3px', textDecoration: 'none' }}
            >
              Open GitHub <ExternalLink size={10} />
            </a>
          </div>
        </div>

        {/* GitHub Actions Checks */}
        <div style={{ marginBottom: '10px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, color: '#475569', marginBottom: '6px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>GITHUB CHECKS</span>
            <button
              className="icon-btn"
              title="Refresh Checks"
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
                  borderRadius: '4px',
                  background: '#ffffff',
                  border: '1px solid #e2e8f0',
                  fontSize: '11px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    {check.status === 'PASSED' && <CheckCircle2 size={12} color="#16a34a" />}
                    {check.status === 'FAILED' && <AlertCircle size={12} color="#dc2626" />}
                    {check.status === 'RUNNING' && <RefreshCw size={12} color="#d97706" className="spin" />}
                    {check.status === 'QUEUED' && <AlertTriangle size={12} color="#64748b" />}
                    <span style={{ fontWeight: 600, color: '#334155' }}>{check.name}</span>
                  </div>
                  <span style={{ fontSize: '9px', fontWeight: 700, color: check.status === 'PASSED' ? '#16a34a' : check.status === 'FAILED' ? '#dc2626' : '#d97706' }}>
                    {check.status}
                  </span>
                </div>

                {check.status === 'FAILED' && (
                  <div style={{ marginTop: '4px', borderTop: '1px dashed #f1f5f9', paddingTop: '4px' }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      style={{ padding: '2px 6px', fontSize: '10px', gap: '3px' }}
                      disabled={diagnosingCheckId === check.id}
                      onClick={() => onDiagnose(check)}
                    >
                      <Sparkles size={10} color="#7c3aed" /> {diagnosingCheckId === check.id ? 'Diagnosing...' : 'AI Failure Diagnosis'}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* AI CI Diagnosis Result Modal/Box */}
        {ciDiagnosisResult && (
          <div style={{ padding: '8px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', fontSize: '11px', marginTop: '10px' }}>
            <div style={{ fontWeight: 700, color: '#991b1b', marginBottom: '4px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>AI Diagnosis: {ciDiagnosisResult.classification}</span>
              <button
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#991b1b' }}
                onClick={onDismissDiagnosis}
              >
                ✕
              </button>
            </div>
            <div style={{ color: '#7f1d1d', marginBottom: '4px' }}>{ciDiagnosisResult.summary}</div>
            <div style={{ fontSize: '10px', color: '#451a03', background: '#fffbeb', padding: '4px', borderRadius: '4px' }}>
              <strong>Suggested Fix:</strong> {ciDiagnosisResult.suggested_fix}
            </div>
          </div>
        )}

        <div style={{ marginTop: '12px' }}>
          <button
            className="btn btn-secondary btn-sm"
            style={{ width: '100%', padding: '4px', fontSize: '11px' }}
            onClick={onOpenPRModal}
          >
            <Plus size={12} /> Create Another PR
          </button>
        </div>
      </div>
    )}
  </div>
);
