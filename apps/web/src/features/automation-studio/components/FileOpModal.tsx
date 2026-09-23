import React from 'react';
import { useTranslation } from 'react-i18next';
import { FileOpModalState } from '../types';

interface FileOpModalProps {
  state: FileOpModalState;
  inputText: string;
  onInputChange: (value: string) => void;
  onClose: () => void;
  onConfirm: () => void;
}

export const FileOpModal: React.FC<FileOpModalProps> = ({
  state,
  inputText,
  onInputChange,
  onClose,
  onConfirm,
}) => {
  const { t } = useTranslation('studioShell');
  return (
    <div className="modal-overlay">
      <div className="modal-dialog" style={{ maxWidth: '420px' }}>
        <div className="modal-header">
          <h3 style={{ fontSize: '14px', fontWeight: 700 }}>
            {state.type === 'create_file' && t('fileOpModal.createFileTitle')}
            {state.type === 'create_folder' && t('fileOpModal.createFolderTitle')}
            {state.type === 'rename' && t('fileOpModal.renameTitle')}
            {state.type === 'delete' && t('fileOpModal.deleteTitle')}
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
          {state.type === 'delete' ? (
            <p style={{ fontSize: '13px', color: '#dc2626' }}>
              {t('fileOpModal.deleteConfirmPrefix')} <code>{state.targetPath}</code>
              {t('fileOpModal.deleteConfirmSuffix')}
            </p>
          ) : (
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">
                {state.type === 'create_file' && t('fileOpModal.filePathLabel')}
                {state.type === 'create_folder' && t('fileOpModal.directoryPathLabel')}
                {state.type === 'rename' && t('fileOpModal.newPathLabel')}
              </label>
              <input
                autoFocus
                type="text"
                className="form-control"
                value={inputText}
                onChange={(e) => onInputChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onConfirm();
                  if (e.key === 'Escape') onClose();
                }}
              />
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary btn-sm" onClick={onClose}>
            {t('common:cancel')}
          </button>
          <button
            className={`btn btn-sm ${state.type === 'delete' ? 'btn-danger' : 'btn-primary'}`}
            style={state.type === 'delete' ? { background: '#dc2626', color: '#fff' } : {}}
            onClick={onConfirm}
          >
            {state.type === 'delete' ? t('common:delete') : t('common:confirm')}
          </button>
        </div>
      </div>
    </div>
  );
};
