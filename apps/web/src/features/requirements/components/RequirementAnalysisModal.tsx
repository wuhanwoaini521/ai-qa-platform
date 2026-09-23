import React from 'react';
import { AlertTriangle, HelpCircle, RefreshCw, Sparkles } from 'lucide-react';
import { RequirementAnalysisDTO } from '../../../types';

interface RequirementAnalysisModalProps {
  isOpen: boolean;
  analyzing: boolean;
  analysis: RequirementAnalysisDTO | null;
  onClose: () => void;
}

export const RequirementAnalysisModal: React.FC<RequirementAnalysisModalProps> = ({
  isOpen,
  analyzing: analyzingReq,
  analysis: aiAnalysis,
  onClose,
}) => {
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '650px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="var(--color-primary)" />
                <h3>AI Requirement Testability Analysis</h3>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={onClose}>
                Close
              </button>
            </div>
            <div className="modal-body">
              {analyzingReq ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <RefreshCw size={24} className="spinning" style={{ marginBottom: '0.75rem' }} />
                  <div>Analyzing requirement testability dimensions...</div>
                </div>
              ) : aiAnalysis ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                      Executive Testing Summary
                    </h4>
                    <p style={{ marginTop: '0.25rem', fontSize: '0.9rem' }}>{aiAnalysis.summary}</p>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--color-error)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <AlertTriangle size={14} /> Identified Quality Risks
                    </h4>
                    <ul style={{ paddingLeft: '1.25rem', marginTop: '0.25rem', fontSize: '0.85rem' }}>
                      {aiAnalysis.risks.map((risk, idx) => (
                        <li key={idx} style={{ marginBottom: '0.25rem' }}>{risk}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--color-warning)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <HelpCircle size={14} /> Ambiguities & Missing Specs
                    </h4>
                    <ul style={{ paddingLeft: '1.25rem', marginTop: '0.25rem', fontSize: '0.85rem' }}>
                      {aiAnalysis.ambiguities.map((amb, idx) => (
                        <li key={idx} style={{ marginBottom: '0.25rem' }}>{amb}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                      Recommended Coverage Dimensions
                    </h4>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '0.4rem' }}>
                      {aiAnalysis.suggested_test_dimensions.map((dim, idx) => (
                        <span key={idx} className="status-pill status-pill-draft">{dim}</span>
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
