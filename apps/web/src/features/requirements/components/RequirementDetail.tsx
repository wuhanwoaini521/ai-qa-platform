import React from 'react';
import { ExternalLink, FileText, Sparkles } from 'lucide-react';
import { Requirement, RequirementStatus } from '../../../types';

interface RequirementDetailProps {
  selectedReq: Requirement;
  onAnalyze: () => void;
  onUpdateStatus: (reqId: string, status: RequirementStatus) => void;
}

export const RequirementDetail: React.FC<RequirementDetailProps> = ({
  selectedReq,
  onAnalyze,
  onUpdateStatus,
}) => {
  return (
    <div className="card">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <FileText size={16} color="#2563eb" />
          <span className="card-title">{selectedReq.title}</span>
          {selectedReq.external_system === 'JIRA' && selectedReq.external_id && (
            <a
              href={selectedReq.external_url || `https://jira.example.com/browse/${selectedReq.external_id}`}
              target="_blank"
              rel="noreferrer"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', background: '#dbeafe', color: '#1e40af', padding: '2px 8px', borderRadius: '4px', textDecoration: 'none', fontWeight: 600 }}
            >
              {selectedReq.external_id} <ExternalLink size={11} />
            </a>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button className="btn btn-secondary btn-sm" onClick={onAnalyze}>
            <Sparkles size={13} color="var(--color-primary)" />
            <span>AI Analyze</span>
          </button>
          <select
            className="form-select"
            style={{ padding: '3px 8px', fontSize: '12px', width: 'auto', margin: 0 }}
            value={selectedReq.status}
            onChange={(e) => onUpdateStatus(selectedReq.id, e.target.value as RequirementStatus)}
          >
            <option value="DRAFT">DRAFT</option>
            <option value="READY">READY</option>
            <option value="ARCHIVED">ARCHIVED</option>
          </select>
        </div>
      </div>
      <div className="card-body">
        <div style={{ marginBottom: '14px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
            Description
          </div>
          <div style={{ fontSize: '13px', color: '#334155', whiteSpace: 'pre-wrap' }}>
            {selectedReq.description || 'No description provided.'}
          </div>
        </div>

        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
            Acceptance Criteria
          </div>
          <div
            style={{
              fontSize: '13px',
              background: '#f8fafc',
              padding: '10px 14px',
              borderRadius: '4px',
              border: '1px solid var(--border-color)',
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
            }}
          >
            {selectedReq.acceptance_criteria || 'No acceptance criteria specified.'}
          </div>
        </div>
      </div>
    </div>
  );
};
