import React from 'react';
import { GitPullRequest, Sparkles } from 'lucide-react';

interface PullRequestModalProps {
  currentBranch: string;
  title: string;
  body: string;
  suggesting: boolean;
  creating: boolean;
  onTitleChange: (value: string) => void;
  onBodyChange: (value: string) => void;
  onClose: () => void;
  onRegenerate: () => void;
  onCreate: () => void;
}

export const PullRequestModal: React.FC<PullRequestModalProps> = ({
  currentBranch,
  title,
  body,
  suggesting,
  creating,
  onTitleChange,
  onBodyChange,
  onClose,
  onRegenerate,
  onCreate,
}) => (
  <div className="modal-overlay">
    <div className="modal-dialog" style={{ maxWidth: '580px' }}>
      <div className="modal-header">
        <h3 style={{ fontSize: '14px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
          <GitPullRequest size={16} color="#059669" /> Create Pull Request
        </h3>
        <button
          type="button"
          style={{ background: 'none', border: 'none', cursor: 'pointer' }}
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      <div className="modal-body" style={{ padding: '16px' }}>
        <div style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '12px', color: '#475569' }}>
            Branch: <code>{currentBranch}</code> → <code>main</code>
          </span>
          <button
            className="btn btn-secondary btn-sm"
            style={{ padding: '2px 8px', fontSize: '11px', gap: '4px' }}
            disabled={suggesting}
            onClick={onRegenerate}
          >
            <Sparkles size={11} color="#7c3aed" /> {suggesting ? 'Generating...' : 'Re-generate AI Summary'}
          </button>
        </div>

        <div className="form-group">
          <label className="form-label">PR Title:</label>
          <input
            type="text"
            className="form-control"
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">PR Body (Markdown):</label>
          <textarea
            rows={8}
            className="form-control"
            style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
            value={body}
            onChange={(e) => onBodyChange(e.target.value)}
          />
        </div>
      </div>
      <div className="modal-footer">
        <button className="btn btn-secondary btn-sm" onClick={onClose}>
          Cancel
        </button>
        <button
          className="btn btn-primary btn-sm"
          style={{ background: '#059669', borderColor: '#059669' }}
          disabled={!title.trim() || creating}
          onClick={onCreate}
        >
          {creating ? 'Creating PR...' : 'Create Pull Request'}
        </button>
      </div>
    </div>
  </div>
);
