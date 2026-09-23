import React from 'react';
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
}) => (
  <div className="modal-overlay">
    <div className="modal-dialog" style={{ maxWidth: '420px' }}>
      <div className="modal-header">
        <h3 style={{ fontSize: '14px', fontWeight: 700 }}>
          {state.type === 'create_file' && 'Create New File'}
          {state.type === 'create_folder' && 'Create New Folder'}
          {state.type === 'rename' && 'Rename File / Directory'}
          {state.type === 'delete' && 'Confirm Delete'}
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
            Are you sure you want to permanently delete <code>{state.targetPath}</code>?
          </p>
        ) : (
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">
              {state.type === 'create_file' && 'File path relative to workspace root:'}
              {state.type === 'create_folder' && 'Directory path relative to workspace root:'}
              {state.type === 'rename' && 'New relative path:'}
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
          Cancel
        </button>
        <button
          className={`btn btn-sm ${state.type === 'delete' ? 'btn-danger' : 'btn-primary'}`}
          style={state.type === 'delete' ? { background: '#dc2626', color: '#fff' } : {}}
          onClick={onConfirm}
        >
          {state.type === 'delete' ? 'Delete' : 'Confirm'}
        </button>
      </div>
    </div>
  </div>
);
