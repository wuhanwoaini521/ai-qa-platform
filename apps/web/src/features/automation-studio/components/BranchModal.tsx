import React from 'react';
import { useTranslation } from 'react-i18next';
import { GitBranch } from 'lucide-react';

interface BranchModalProps {
  branchName: string;
  currentBranch: string;
  onBranchNameChange: (value: string) => void;
  onClose: () => void;
  onConfirm: () => void;
}

export const BranchModal: React.FC<BranchModalProps> = ({
  branchName,
  currentBranch,
  onBranchNameChange,
  onClose,
  onConfirm,
}) => {
  const { t } = useTranslation('studioShell');
  return (
    <div className="modal-overlay">
      <div className="modal-dialog" style={{ maxWidth: '440px' }}>
        <div className="modal-header">
          <h3 style={{ fontSize: '14px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <GitBranch size={16} color="var(--accent-blue)" /> {t('branchModal.title')}
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
          <div className="form-group">
            <label className="form-label">
              {t('branchModal.nameLabelPrefix')} <code>qa/C12345-auth-test</code>
              {t('branchModal.nameLabelSuffix')}
            </label>
            <input
              autoFocus
              type="text"
              className="form-control"
              value={branchName}
              onChange={(e) => onBranchNameChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onConfirm();
                if (e.key === 'Escape') onClose();
              }}
            />
          </div>
          <div style={{ fontSize: '11px', color: 'var(--ink-muted)' }}>
            {t('branchModal.basedOnPrefix')} <code>{currentBranch}</code>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary btn-sm" onClick={onClose}>
            {t('common:cancel')}
          </button>
          <button
            className="btn btn-primary btn-sm"
            disabled={!branchName.trim()}
            onClick={onConfirm}
          >
            {t('branchModal.createAndSwitch')}
          </button>
        </div>
      </div>
    </div>
  );
};
