import React from 'react';
import { Code2, Edit3, ExternalLink, Play, Sparkles } from 'lucide-react';
import { AutomationBinding, GenerateAutomationResponse } from '../../../types';
import { GeneratedCodePreview } from './GeneratedCodePreview';

interface AutomationBindingPanelProps {
  selectedBinding: AutomationBinding | null;
  generatedDraft: GenerateAutomationResponse | null;
  savingDraft: boolean;
  runningCase: boolean;
  generating: boolean;
  runMessage: string | null;
  onNavigateToStudio?: (filePath: string) => void;
  onOpenBindingModal: () => void;
  onRunTestCase: () => void;
  onGenerateAutomation: () => void;
  onSaveDraftToWorkspace: () => void;
}

export const AutomationBindingPanel: React.FC<AutomationBindingPanelProps> = ({
  selectedBinding,
  generatedDraft,
  savingDraft,
  runningCase,
  generating,
  runMessage,
  onNavigateToStudio,
  onOpenBindingModal,
  onRunTestCase,
  onGenerateAutomation,
  onSaveDraftToWorkspace,
}) => {
  return (
    <div className="card">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Code2 size={16} color="#2563eb" />
          <span className="card-title">Automation Binding & Execution</span>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={onOpenBindingModal}
          >
            <Edit3 size={13} /> {selectedBinding ? 'Edit Binding' : 'Configure Binding'}
          </button>
        </div>
      </div>
      <div className="card-body">
        {selectedBinding ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', background: '#f8fafc', padding: '12px', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Target Test File</div>
                <div style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: '#0f172a', marginTop: '2px' }}>
                  {selectedBinding.file_path}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Pytest Node ID</div>
                <div style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: '#0f172a', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {selectedBinding.nodeid}
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onNavigateToStudio && onNavigateToStudio(selectedBinding.file_path)}
              >
                <ExternalLink size={13} /> Open in Studio
              </button>
              <button
                className="btn btn-primary btn-sm"
                disabled={runningCase}
                onClick={onRunTestCase}
              >
                <Play size={13} /> {runningCase ? 'Running...' : 'Run Test Now'}
              </button>
              <button
                className="btn btn-secondary btn-sm"
                disabled={generating}
                onClick={onGenerateAutomation}
              >
                <Sparkles size={13} color="#9333ea" /> Re-generate AI Code
              </button>
            </div>

            {runMessage && (
              <div style={{ marginTop: '8px', padding: '8px 12px', background: '#eff6ff', borderRadius: '4px', fontSize: '12px', color: '#1d4ed8' }}>
                {runMessage}
              </div>
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '16px' }}>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '14px' }}>
              This test case is currently manual and not yet bound to an automated test file.
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '10px' }}>
              <button
                className="btn btn-primary"
                disabled={generating}
                onClick={onGenerateAutomation}
              >
                <Sparkles size={15} /> {generating ? 'Generating Playwright Code...' : 'Generate Automation Scaffold'}
              </button>
            </div>
          </div>
        )}

        {/* AI Generated Code Preview */}
        {generatedDraft && (
          <GeneratedCodePreview
            generatedDraft={generatedDraft}
            savingDraft={savingDraft}
            onSaveDraftToWorkspace={onSaveDraftToWorkspace}
          />
        )}
      </div>
    </div>
  );
};
