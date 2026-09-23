import React from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronRight } from 'lucide-react';
import { Requirement } from '../../../types';

interface RequirementListProps {
  requirements: Requirement[];
  loading: boolean;
  selectedReq: Requirement | null;
  onSelect: (requirement: Requirement) => void;
}

export const RequirementList: React.FC<RequirementListProps> = ({
  requirements,
  loading,
  selectedReq,
  onSelect,
}) => {
  const { t } = useTranslation('requirements');
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">{t('listTitle', { total: requirements.length })}</span>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {loading ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {t('listLoading')}
          </div>
        ) : requirements.length === 0 ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {t('listEmpty')}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {requirements.map((r) => {
              const isSelected = selectedReq?.id === r.id;
              return (
                <div
                  key={r.id}
                  onClick={() => onSelect(r)}
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
                      {r.title}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
                      <span className="status-pill status-pill-draft">{r.status}</span>
                      {r.external_system === 'JIRA' && r.external_id && (
                        <span style={{ fontSize: '11px', background: '#dbeafe', color: '#1e40af', padding: '1px 6px', borderRadius: '4px', fontWeight: 600 }}>
                          {t('listJiraBadge', { id: r.external_id })}
                        </span>
                      )}
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {new Date(r.created_at).toLocaleDateString()}
                      </span>
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
