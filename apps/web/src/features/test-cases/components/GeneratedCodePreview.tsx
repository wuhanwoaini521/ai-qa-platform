import React from 'react';
import { CheckCircle } from 'lucide-react';
import { GenerateAutomationResponse } from '../../../types';

interface GeneratedCodePreviewProps {
  generatedDraft: GenerateAutomationResponse;
  savingDraft: boolean;
  onSaveDraftToWorkspace: () => void;
}

export const GeneratedCodePreview: React.FC<GeneratedCodePreviewProps> = ({
  generatedDraft,
  savingDraft,
  onSaveDraftToWorkspace,
}) => {
  return (
    <div style={{ marginTop: '18px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <div style={{ fontSize: '12px', fontWeight: 700, color: '#334155' }}>
          AI Generated Test Scaffold ({generatedDraft.target_file})
        </div>
        <button
          className="btn btn-primary btn-sm"
          disabled={savingDraft}
          onClick={onSaveDraftToWorkspace}
        >
          <CheckCircle size={13} /> {savingDraft ? 'Saving to Workspace...' : 'Save & Bind to Workspace'}
        </button>
      </div>
      <div
        style={{
          background: '#0f172a',
          color: '#f8fafc',
          padding: '12px',
          borderRadius: '6px',
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          overflowX: 'auto',
          maxHeight: '260px',
        }}
      >
        <pre>{generatedDraft.suggested_code}</pre>
      </div>
    </div>
  );
};
