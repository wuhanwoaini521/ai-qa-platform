import React from 'react';
import { useTranslation } from 'react-i18next';
import { CheckSquare, ExternalLink, Sparkles, Tag } from 'lucide-react';
import { AutomationStatus, TestCase } from '../../../types';
import { ModernCasePanel } from '../../lifecycle/ModernCasePanel';

interface TestCaseDetailProps {
  selectedCase: TestCase;
  onUpdateStatus: (caseId: string, automationStatus: AutomationStatus) => void;
  onOptimize?: () => void;
  onReview?: () => void;
  aiDisabled?: boolean;
}

export const TestCaseDetail: React.FC<TestCaseDetailProps> = ({
  selectedCase,
  onUpdateStatus,
  onOptimize,
  onReview,
  aiDisabled,
}) => {
  const { t } = useTranslation('testCases');
  return (
    <div className="card test-case-detail">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <CheckSquare size={16} color="#16a34a" />
          <span className="card-title">{selectedCase.title}</span>
          {selectedCase.external_case_id && (
            <a
              href={selectedCase.external_url || `https://testrail.example.com/index.php?/cases/view/${selectedCase.external_case_id.replace(/^C/i, '')}`}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: '11px', background: '#ecfdf5', color: '#047857', padding: '2px 8px', borderRadius: '4px', textDecoration: 'none', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px' }}
            >
              {selectedCase.external_case_id} <ExternalLink size={11} />
            </a>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button className="btn btn-secondary btn-sm" type="button" disabled={aiDisabled} title={aiDisabled ? t('tasks:bindingRequired') : undefined} onClick={onOptimize}><Sparkles size={13} /> {t('tasks:optimizeAction')}</button>
          <button className="btn btn-secondary btn-sm" type="button" disabled={aiDisabled} title={aiDisabled ? t('tasks:bindingRequired') : undefined} onClick={onReview}><Sparkles size={13} /> {t('tasks:reviewAction')}</button>
          <span className={`badge badge-${selectedCase.priority.toLowerCase()}`}>
            {selectedCase.priority}
          </span>
          <select
            className="form-control"
            style={{ padding: '3px 8px', fontSize: '12px', width: '130px' }}
            value={selectedCase.automation_status}
            onChange={(e) =>
              onUpdateStatus(selectedCase.id, e.target.value as AutomationStatus)
            }
          >
            <option value="MANUAL">MANUAL</option>
            <option value="DRAFT">DRAFT</option>
            <option value="AUTOMATED">AUTOMATED</option>
          </select>
        </div>
      </div>
      <div className="card-body">
        {selectedCase.test_model && <ModernCasePanel key={selectedCase.id} item={selectedCase}/>}
        {selectedCase.preconditions && (
          <div style={{ marginBottom: '14px' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
              {t('preconditions')}
            </div>
            <div style={{ fontSize: '13px', color: '#334155', background: '#f8fafc', padding: '8px 12px', borderRadius: '4px' }}>
              {selectedCase.preconditions}
            </div>
          </div>
        )}

        <div style={{ marginBottom: '14px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
            {t('testSteps', { total: selectedCase.steps.length })}
          </div>
          {selectedCase.steps.length > 0 ? (
            <ol style={{ paddingLeft: '20px', fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {selectedCase.steps.map((st, i) => (
                <li key={i} style={{ color: '#1e293b' }}>
                  {st}
                </li>
              ))}
            </ol>
          ) : (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{t('noSteps')}</div>
          )}
        </div>

        <div style={{ marginBottom: '14px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
            {t('expectedResult')}
          </div>
          <div style={{ fontSize: '13px', color: '#334155', background: '#f0fdf4', border: '1px solid #bbf7d0', padding: '8px 12px', borderRadius: '4px' }}>
            {selectedCase.expected_result || t('noExpectedResult')}
          </div>
        </div>

        {selectedCase.tags.length > 0 && (
          <div>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
              {t('tags')}
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {selectedCase.tags.map((tag, idx) => (
                <span key={idx} className="badge badge-draft">
                  <Tag size={10} style={{ marginRight: '4px' }} /> {tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
