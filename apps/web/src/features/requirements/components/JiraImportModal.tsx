import React from 'react';
import { useTranslation } from 'react-i18next';
import { Download, RefreshCw, Search } from 'lucide-react';
import { JiraIssue } from '../../../types';

interface JiraImportModalProps {
  isOpen: boolean;
  issues: JiraIssue[];
  searchQuery: string;
  loading: boolean;
  importing: boolean;
  selectedKeys: string[];
  onSearch: (query: string) => void;
  onToggleKey: (key: string) => void;
  onImport: () => void;
  onClose: () => void;
}

export const JiraImportModal: React.FC<JiraImportModalProps> = ({
  isOpen,
  issues: jiraIssues,
  searchQuery: jiraSearchQuery,
  loading: loadingJira,
  importing: importingJira,
  selectedKeys: selectedJiraKeys,
  onSearch: handleSearchJira,
  onToggleKey: handleToggleJiraKey,
  onImport: handleImportJira,
  onClose,
}) => {
  const { t } = useTranslation('requirements');
  return (
    <>
      {isOpen && (
        <div className="modal-backdrop">
          <div className="modal" style={{ maxWidth: '700px', width: '90%' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Download size={18} color="var(--accent-blue)" />
                <h3 className="modal-title">{t('jiraTitle')}</h3>
              </div>
              <button
                className="btn btn-icon"
                onClick={onClose}
                style={{ padding: '4px' }}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <div style={{ marginBottom: '16px', display: 'flex', gap: '8px' }}>
                <div style={{ position: 'relative', flex: 1 }}>
                  <input
                    type="text"
                    className="form-input"
                    placeholder={t('jiraSearchPlaceholder')}
                    value={jiraSearchQuery}
                    onChange={(e) => handleSearchJira(e.target.value)}
                    style={{ paddingLeft: '32px' }}
                  />
                  <Search size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: 'var(--ink-faint)' }} />
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={() => handleSearchJira(jiraSearchQuery)}
                  disabled={loadingJira}
                >
                  <RefreshCw size={14} className={loadingJira ? 'spin' : ''} /> {t('common:refresh')}
                </button>
              </div>

              {loadingJira ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {t('jiraLoading')}
                </div>
              ) : jiraIssues.length === 0 ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {t('jiraEmpty')}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '350px', overflowY: 'auto' }}>
                  {jiraIssues.map((issue) => {
                    const isChecked = selectedJiraKeys.includes(issue.key);
                    return (
                      <div
                        key={issue.key}
                        onClick={() => handleToggleJiraKey(issue.key)}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '12px',
                          padding: '10px 14px',
                          borderRadius: 'var(--r-xs)',
                          border: isChecked ? '1px solid var(--accent-blue)' : '1px solid var(--border-color)',
                          backgroundColor: isChecked ? 'var(--accent-blue-soft)' : 'var(--bg-surface)',
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => {}} // Handled by outer div
                          style={{ marginTop: '3px' }}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--accent-blue)' }}>
                              {issue.key}
                            </span>
                            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                              {issue.summary}
                            </span>
                          </div>
                          {issue.description && (
                            <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '4px 0 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {issue.description}
                            </p>
                          )}
                          <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                            <span style={{ fontSize: '10px', background: 'var(--surface-inset)', color: 'var(--ink-muted)', padding: '1px 5px', borderRadius: 'var(--r-xs)' }}>
                              {issue.status}
                            </span>
                            <span style={{ fontSize: '10px', background: 'var(--accent-red-soft)', color: 'var(--accent-red)', padding: '1px 5px', borderRadius: 'var(--r-xs)' }}>
                              {issue.priority}
                            </span>
                            {issue.labels.map((lbl) => (
                              <span key={lbl} style={{ fontSize: '10px', background: 'var(--surface-inset)', color: 'var(--ink-muted)', padding: '1px 5px', borderRadius: 'var(--r-xs)' }}>
                                #{lbl}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginRight: 'auto' }}>
                {t('jiraSelected', { total: selectedJiraKeys.length })}
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
              >
                {t('common:cancel')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={selectedJiraKeys.length === 0 || importingJira}
                onClick={handleImportJira}
              >
                {importingJira ? t('jiraImporting') : t('jiraImport', { total: selectedJiraKeys.length })}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
