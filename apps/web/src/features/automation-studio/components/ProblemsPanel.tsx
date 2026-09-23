import React from 'react';
import { useTranslation } from 'react-i18next';
import { AlertCircle, AlertTriangle, Terminal } from 'lucide-react';
import { ValidationIssue } from '../../../types';

interface ProblemsPanelProps {
  issues: ValidationIssue[];
  expanded: boolean;
  onToggle: () => void;
  onJumpToIssue: (issue: ValidationIssue) => void;
}

export const ProblemsPanel: React.FC<ProblemsPanelProps> = ({
  issues,
  expanded,
  onToggle,
  onJumpToIssue,
}) => {
  const { t } = useTranslation('studioPanels');

  return (
    <>
      <div
        style={{
          padding: '6px 12px',
          background: '#f8fafc',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          fontSize: '12px',
          fontWeight: 600,
        }}
        onClick={onToggle}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Terminal size={14} color="#64748b" />
          <span>{t('problems.title')}</span>
          {issues.length > 0 ? (
            <span className="badge badge-p0" style={{ fontSize: '10px' }}>
              {t('problems.issuesCount', { count: issues.length })}
            </span>
          ) : (
            <span className="badge badge-ready" style={{ fontSize: '10px' }}>
              {t('problems.noErrors')}
            </span>
          )}
        </div>
        <span style={{ fontSize: '11px', color: 'var(--primary)' }}>
          {expanded ? t('problems.collapse') : t('problems.expand')}
        </span>
      </div>

      {expanded && (
        <div style={{ height: '140px', overflowY: 'auto', padding: '8px' }}>
          {issues.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#16a34a', padding: '16px', fontSize: '12px' }}>
              {t('problems.allValid')}
            </div>
          ) : (
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
                    style={{ cursor: 'pointer' }}
                    onClick={() => onJumpToIssue(issue)}
                  >
                    <td style={{ padding: '4px 8px' }}>
                      {issue.severity === 'error' ? (
                        <span style={{ color: '#ef4444', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <AlertCircle size={12} /> {t('problems.error')}
                        </span>
                      ) : (
                        <span style={{ color: '#d97706', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <AlertTriangle size={12} /> {t('problems.warning')}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '4px 8px', fontFamily: 'var(--font-mono)' }}>{issue.file}</td>
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
