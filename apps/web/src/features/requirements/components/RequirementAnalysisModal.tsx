import React from 'react';
import { AIExecutionTimeline } from '../../../components/AIExecutionTimeline';
import type { AITraceEvent } from '../../../types';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, HelpCircle, Sparkles } from 'lucide-react';
import { RequirementAnalysisDTO } from '../../../types';

interface RequirementAnalysisModalProps {
  isOpen: boolean;
  progressEvents: AITraceEvent[];
  progressError: string;
  analyzing: boolean;
  analysis: RequirementAnalysisDTO | null;
  onClose: () => void;
}

export const RequirementAnalysisModal: React.FC<
  RequirementAnalysisModalProps
> = ({
  isOpen,
  progressEvents,
  progressError,
  analyzing: analyzingReq,
  analysis: aiAnalysis,
  onClose,
}) => {
  const { t } = useTranslation('requirements');
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '650px' }}>
            <div className="modal-header">
              <div
                style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
              >
                <Sparkles size={18} color="var(--color-primary)" />
                <h3>{t('analysisTitle')}</h3>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={onClose}>
                {t('common:close')}
              </button>
            </div>
            <div className="modal-body">
              <AIExecutionTimeline
                events={progressEvents}
                running={analyzingReq}
              />
              {progressError && <p role="alert">{progressError}</p>}
              {analyzingReq ? null : aiAnalysis ? (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '1rem',
                  }}
                >
                  <div>
                    <h4
                      style={{
                        fontSize: '0.85rem',
                        color: 'var(--text-muted)',
                        textTransform: 'uppercase',
                      }}
                    >
                      {t('analysisSummaryHeading')}
                    </h4>
                    <p style={{ marginTop: '0.25rem', fontSize: '0.9rem' }}>
                      {aiAnalysis.summary}
                    </p>
                  </div>

                  <div>
                    <h4
                      style={{
                        fontSize: '0.85rem',
                        color: 'var(--color-error)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <AlertTriangle size={14} /> {t('analysisRisksHeading')}
                    </h4>
                    <ul
                      style={{
                        paddingLeft: '1.25rem',
                        marginTop: '0.25rem',
                        fontSize: '0.85rem',
                      }}
                    >
                      {aiAnalysis.risks.map((risk, idx) => (
                        <li key={idx} style={{ marginBottom: '0.25rem' }}>
                          {risk}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4
                      style={{
                        fontSize: '0.85rem',
                        color: 'var(--color-warning)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <HelpCircle size={14} /> {t('analysisAmbiguitiesHeading')}
                    </h4>
                    <ul
                      style={{
                        paddingLeft: '1.25rem',
                        marginTop: '0.25rem',
                        fontSize: '0.85rem',
                      }}
                    >
                      {aiAnalysis.ambiguities.map((amb, idx) => (
                        <li key={idx} style={{ marginBottom: '0.25rem' }}>
                          {amb}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4
                      style={{
                        fontSize: '0.85rem',
                        color: 'var(--text-muted)',
                        textTransform: 'uppercase',
                      }}
                    >
                      {t('analysisDimensionsHeading')}
                    </h4>
                    <div
                      style={{
                        display: 'flex',
                        gap: '6px',
                        flexWrap: 'wrap',
                        marginTop: '0.4rem',
                      }}
                    >
                      {aiAnalysis.suggested_test_dimensions.map((dim, idx) => (
                        <span
                          key={idx}
                          className="status-pill status-pill-draft"
                        >
                          {dim}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </>
  );
};
