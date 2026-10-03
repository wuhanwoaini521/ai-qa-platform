import React from 'react';
import { AIExecutionTimeline } from '../../../components/AIExecutionTimeline';
import type { AITraceEvent } from '../../../types';
import { useTranslation } from 'react-i18next';
import { Code2, Edit3, ExternalLink, Play, Sparkles } from 'lucide-react';
import { AutomationBinding, GenerateAutomationResponse } from '../../../types';
import { GeneratedCodePreview } from './GeneratedCodePreview';

interface AutomationBindingPanelProps {
  selectedBinding: AutomationBinding | null;
  generatedDraft: GenerateAutomationResponse | null;
  savingDraft: boolean;
  runningCase: boolean;
  generating: boolean;
  progressEvents: AITraceEvent[];
  progressError: string;
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
  progressEvents,
  progressError,
  runMessage,
  onNavigateToStudio,
  onOpenBindingModal,
  onRunTestCase,
  onGenerateAutomation,
  onSaveDraftToWorkspace,
}) => {
  const { t } = useTranslation('testCases');
  return (
    <div className="card">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Code2 size={16} color="var(--accent-blue)" />
          <span className="card-title">{t('bindingTitle')}</span>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={onOpenBindingModal}
          >
            <Edit3 size={13} />{' '}
            {selectedBinding ? t('bindingEdit') : t('bindingConfigure')}
          </button>
        </div>
      </div>
      <div className="card-body">
        <AIExecutionTimeline events={progressEvents} running={generating} />
        {progressError && <p role="alert">{progressError}</p>}
        {selectedBinding ? (
          <div
            style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}
          >
            <div
              className="automation-binding-info-grid"
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '12px',
                background: 'var(--surface-inset)',
                padding: '12px',
                borderRadius: 'var(--r-xs)',
                border: '1px solid var(--border-color)',
              }}
            >
              <div className="automation-binding-info-field">
                <div
                  style={{
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    fontWeight: 600,
                  }}
                >
                  {t('bindingTargetFile')}
                </div>
                <div
                  className="automation-binding-info-value"
                  style={{
                    fontSize: '12px',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--ink)',
                    marginTop: '2px',
                  }}
                >
                  {selectedBinding.file_path}
                </div>
              </div>
              <div className="automation-binding-info-field">
                <div
                  style={{
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    fontWeight: 600,
                  }}
                >
                  {t('bindingNodeId')}
                </div>
                <div
                  className="automation-binding-info-value"
                  style={{
                    fontSize: '12px',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--ink)',
                    marginTop: '2px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {selectedBinding.nodeid}
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() =>
                  onNavigateToStudio &&
                  onNavigateToStudio(selectedBinding.file_path)
                }
              >
                <ExternalLink size={13} /> {t('common:openInStudio')}
              </button>
              <button
                className="btn btn-primary btn-sm"
                disabled={runningCase}
                onClick={onRunTestCase}
              >
                <Play size={13} />{' '}
                {runningCase ? t('bindingRunning') : t('bindingRunNow')}
              </button>
              <button
                className="btn btn-secondary btn-sm"
                disabled={generating}
                onClick={onGenerateAutomation}
              >
                <Sparkles size={13} color="var(--accent-violet)" /> {t('bindingRegenerate')}
              </button>
            </div>

            {runMessage && (
              <div
                style={{
                  marginTop: '8px',
                  padding: '8px 12px',
                  background: 'var(--accent-blue-soft)',
                  borderRadius: 'var(--r-xs)',
                  fontSize: '12px',
                  color: 'var(--accent-blue)',
                }}
              >
                {runMessage}
              </div>
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '16px' }}>
            <p
              style={{
                fontSize: '13px',
                color: 'var(--text-muted)',
                marginBottom: '14px',
              }}
            >
              {t('bindingManualHint')}
            </p>
            <div
              style={{ display: 'flex', justifyContent: 'center', gap: '10px' }}
            >
              <button
                className="btn btn-primary"
                disabled={generating}
                onClick={onGenerateAutomation}
              >
                <Sparkles size={15} />{' '}
                {generating ? t('bindingGenerating') : t('bindingGenerate')}
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
