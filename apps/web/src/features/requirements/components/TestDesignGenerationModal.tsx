import React from 'react';
import { RefreshCw, Sparkles } from 'lucide-react';
import { TestDesignSuggestion } from '../../../types';

interface TestDesignGenerationModalProps {
  isOpen: boolean;
  generating: boolean;
  suggestions: TestDesignSuggestion[];
  onAdopt: (suggestion: TestDesignSuggestion) => void;
  onClose: () => void;
}

export const TestDesignGenerationModal: React.FC<TestDesignGenerationModalProps> = ({
  isOpen,
  generating: generatingDesigns,
  suggestions: suggestedDesigns,
  onAdopt: handleAdoptDesign,
  onClose,
}) => {
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '750px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="var(--color-primary)" />
                <h3>AI Generated Test Design Candidates</h3>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={onClose}>
                Close
              </button>
            </div>
            <div className="modal-body">
              {generatingDesigns ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <RefreshCw size={24} className="spinning" style={{ marginBottom: '0.75rem' }} />
                  <div>Generating functional, boundary, negative, and API test designs...</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {suggestedDesigns.map((sug, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '1rem',
                        background: 'var(--bg-subtle)',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div style={{ flex: 1, paddingRight: '1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="status-pill status-pill-draft">{sug.category}</span>
                          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{sug.title}</span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Risk: {sug.risk}</span>
                        </div>
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
                          {sug.description}
                        </p>
                      </div>
                      <button className="btn btn-primary btn-sm" onClick={() => handleAdoptDesign(sug)}>
                        Adopt Design
                      </button>
                    </div>
                  ))}
                  {suggestedDesigns.length === 0 && (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      All design candidates adopted or none generated.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};
