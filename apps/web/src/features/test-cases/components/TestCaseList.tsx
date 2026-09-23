import React from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronRight } from 'lucide-react';
import { TestCase } from '../../../types';

interface TestCaseListProps {
  testCases: TestCase[];
  loading: boolean;
  selectedCase: TestCase | null;
  onSelect: (testCase: TestCase) => void;
}

export const TestCaseList: React.FC<TestCaseListProps> = ({
  testCases,
  loading,
  selectedCase,
  onSelect,
}) => {
  const { t } = useTranslation('testCases');
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">{t('listTitle', { total: testCases.length })}</span>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {loading ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {t('listLoading')}
          </div>
        ) : testCases.length === 0 ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {t('listEmpty')}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {testCases.map((tc) => {
              const isSelected = selectedCase?.id === tc.id;
              return (
                <div
                  key={tc.id}
                  onClick={() => onSelect(tc)}
                  style={{
                    padding: '12px 16px',
                    borderBottom: '1px solid var(--border-color)',
                    cursor: 'pointer',
                    backgroundColor: isSelected ? '#eff6ff' : 'transparent',
                    borderLeft: isSelected ? '3px solid var(--primary)' : '3px solid transparent',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1, paddingRight: '8px' }}>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {tc.title}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px', flexWrap: 'wrap' }}>
                      <span className={`badge badge-${tc.priority.toLowerCase()}`}>{tc.priority}</span>
                      <span className={`badge badge-${tc.automation_status.toLowerCase()}`}>
                        {tc.automation_status}
                      </span>
                      {tc.external_case_id && (
                        <span style={{ fontSize: '10px', background: '#ecfdf5', color: '#047857', padding: '1px 5px', borderRadius: '3px', fontWeight: 600 }}>
                          TestRail: {tc.external_case_id}
                        </span>
                      )}
                      {tc.tags && tc.tags.slice(0, 2).map((tag, idx) => (
                        <span key={idx} className="badge badge-draft" style={{ fontSize: '10px' }}>
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <ChevronRight size={16} color={isSelected ? '#2563eb' : '#94a3b8'} />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
