import React from 'react';
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
  return (
    <>
      {isOpen && (
        <div className="modal-backdrop">
          <div className="modal" style={{ maxWidth: '700px', width: '90%' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Download size={18} color="#0284c7" />
                <h3 className="modal-title">Import User Stories from Jira</h3>
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
                    placeholder="Search Jira issues by key, summary, or description..."
                    value={jiraSearchQuery}
                    onChange={(e) => handleSearchJira(e.target.value)}
                    style={{ paddingLeft: '32px' }}
                  />
                  <Search size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: '#94a3b8' }} />
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={() => handleSearchJira(jiraSearchQuery)}
                  disabled={loadingJira}
                >
                  <RefreshCw size={14} className={loadingJira ? 'spin' : ''} /> Refresh
                </button>
              </div>

              {loadingJira ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  Fetching issues from Jira...
                </div>
              ) : jiraIssues.length === 0 ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  No Jira issues found matching the query.
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
                          borderRadius: '6px',
                          border: isChecked ? '1px solid #38bdf8' : '1px solid var(--border-color)',
                          backgroundColor: isChecked ? '#f0f9ff' : 'var(--bg-surface)',
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
                            <span style={{ fontWeight: 700, fontSize: '13px', color: '#0369a1' }}>
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
                            <span style={{ fontSize: '10px', background: '#e2e8f0', color: '#475569', padding: '1px 5px', borderRadius: '3px' }}>
                              {issue.status}
                            </span>
                            <span style={{ fontSize: '10px', background: '#fee2e2', color: '#991b1b', padding: '1px 5px', borderRadius: '3px' }}>
                              {issue.priority}
                            </span>
                            {issue.labels.map((lbl) => (
                              <span key={lbl} style={{ fontSize: '10px', background: '#f1f5f9', color: '#64748b', padding: '1px 5px', borderRadius: '3px' }}>
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
                {selectedJiraKeys.length} selected
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={selectedJiraKeys.length === 0 || importingJira}
                onClick={handleImportJira}
              >
                {importingJira ? 'Importing...' : `Import ${selectedJiraKeys.length} to Requirements`}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
