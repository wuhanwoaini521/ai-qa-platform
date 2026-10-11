import React from 'react';
import { useTranslation } from 'react-i18next';
import { AlertCircle, AlertTriangle, LoaderCircle, Terminal } from 'lucide-react';
import { ValidationIssue } from '../../../types';

interface ProblemsPanelProps {
  issues: ValidationIssue[];
  expanded: boolean;
  validating: boolean;
  hasValidated: boolean;
  validationFailed: boolean;
  onToggle: () => void;
  onValidate: () => void;
  onJumpToIssue: (issue: ValidationIssue) => void;
}

export const ProblemsPanel: React.FC<ProblemsPanelProps> = ({
  issues,
  expanded,
  validating,
  hasValidated,
  validationFailed,
  onToggle,
  onValidate,
  onJumpToIssue,
}) => {
  const { t } = useTranslation('studioPanels');

  return (
    <>
      <button
        type="button"
        className="studio-problems-toggle"
        aria-expanded={expanded}
        aria-controls={expanded ? 'studio-problems-panel' : undefined}
        style={{
          padding: '6px 12px',
          background: 'var(--surface-inset)',
          alignItems: 'center',
          justifyContent: 'space-between',
          width: '100%',
          border: 0,
          textAlign: 'left',
          cursor: 'pointer',
          fontSize: '12px',
          fontWeight: 600,
          color: 'inherit',
          fontFamily: 'inherit',
        }}
        onClick={onToggle}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Terminal size={14} color="var(--ink-muted)" />
          <span>{t('problems.title')}</span>
          {issues.length > 0 ? (
            <span className="badge badge-p0" style={{ fontSize: '10px' }}>
              {t('problems.issuesCount', { count: issues.length })}
            </span>
          ) : validationFailed ? (
            <span className="badge badge-p0" style={{ fontSize: '10px' }}>{t('problems.statusError')}</span>
          ) : hasValidated ? (
            <span className="badge badge-ready" style={{ fontSize: '10px' }}>{t('problems.noErrors')}</span>
          ) : (
            <span className="badge" style={{ fontSize: '10px' }}>{t('problems.statusNotChecked')}</span>
          )}
        </span>
        <span style={{ fontSize: '11px', color: 'var(--primary)' }}>
          {expanded ? t('problems.collapse') : t('problems.expand')}
        </span>
      </button>

      {expanded && (
        <div id="studio-problems-panel" role="region" aria-label={t('problems.title')} style={{ height: '140px', overflowY: 'auto', padding: '8px' }}>
          {validating && <div role="status" aria-live="polite" style={{ display: 'flex', alignItems: 'center', gap: '7px', padding: '12px', color: 'var(--text-muted)', fontSize: '12px' }}><LoaderCircle size={14} aria-hidden="true" />{t('problems.validating')}</div>}
          {validationFailed && !validating && <div role="alert" style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '12px', color: 'var(--ui-rose-strong)', fontSize: '12px' }}><AlertCircle size={14} aria-hidden="true" /><span>{t('problems.validationFailed')}</span><button type="button" className="btn btn-secondary btn-sm" onClick={onValidate}>{t('problems.retryValidation')}</button></div>}
          {!hasValidated && !validationFailed && !validating && <div role="status" style={{ color: 'var(--text-muted)', padding: '16px', fontSize: '12px' }}>{t('problems.notChecked')}</div>}
          {hasValidated && !validationFailed && !validating && issues.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--accent-green)', padding: '16px', fontSize: '12px' }}>
              {t('problems.allValid')}
            </div>
          )}
          {issues.length > 0 && (
            <table className="data-table" style={{ fontSize: '12px' }}>
              <thead>
                <tr>
                  <th style={{ padding: '4px 8px' }}>{t('problems.severity')}</th>
                  <th style={{ padding: '4px 8px' }}>{t('problems.file')}</th>
                  <th style={{ padding: '4px 8px' }}>{t('problems.line')}</th>
                  <th style={{ padding: '4px 8px' }}>{t('problems.message')}</th>
                  <th style={{ padding: '4px 8px' }}>{t('problems.ruleId')}</th>
                </tr>
              </thead>
              <tbody>
                {issues.map((issue, idx) => (
                  <tr
                    key={idx}
                  >
                    <td style={{ padding: '4px 8px' }}>
                      {issue.severity === 'error' ? (
                        <span style={{ color: 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <AlertCircle size={12} /> {t('problems.error')}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--accent-amber)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <AlertTriangle size={12} /> {t('problems.warning')}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '4px 8px' }}><button type="button" onClick={() => onJumpToIssue(issue)} aria-label={t('problems.openFile', { file: issue.file, line: issue.line })} style={{ padding: 0, border: 0, background: 'transparent', color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)', textAlign: 'left', cursor: 'pointer' }}>{issue.file}</button></td>
                    <td style={{ padding: '4px 8px' }}>{issue.line}:{issue.column}</td>
                    <td style={{ padding: '4px 8px' }}>{issue.message}</td>
                    <td style={{ padding: '4px 8px', color: 'var(--text-muted)' }}>{issue.rule_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </>
  );
};
