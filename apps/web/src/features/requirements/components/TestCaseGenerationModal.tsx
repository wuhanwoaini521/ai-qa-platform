import React from 'react';
import { RefreshCw, Sparkles } from 'lucide-react';
import { TestCaseGenerationItem, TestDesign } from '../../../types';

interface TestCaseGenerationModalProps {
  isOpen: boolean;
  generating: boolean;
  activeDesign: TestDesign | null;
  cases: TestCaseGenerationItem[];
  onAdopt: (item: TestCaseGenerationItem) => void;
  onClose: () => void;
}

export const TestCaseGenerationModal: React.FC<TestCaseGenerationModalProps> = ({
  isOpen,
  generating: generatingCases,
  activeDesign: activeDesignForCases,
  cases: suggestedCases,
  onAdopt: handleAdoptCase,
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
                <div>
                  <h3>AI Generated Test Cases</h3>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Design: {activeDesignForCases?.title}
                  </div>
                </div>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={onClose}>
                Close
              </button>
            </div>
            <div className="modal-body">
              {generatingCases ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <RefreshCw size={24} className="spinning" style={{ marginBottom: '0.75rem' }} />
                  <div>Generating concrete test case steps, preconditions, and assertions...</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {suggestedCases.map((c, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '1rem',
                        background: 'var(--bg-subtle)',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{c.title}</div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                            Priority: <strong>{c.priority}</strong> | Tags: {c.tags.join(', ')}
                          </div>
                        </div>
                        <button className="btn btn-primary btn-sm" onClick={() => handleAdoptCase(c)}>
                          Adopt as Draft Case
                        </button>
                      </div>
                      <div style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>
                        <div style={{ fontWeight: 500 }}>Steps:</div>
                        <ol style={{ paddingLeft: '1.25rem', margin: '0.25rem 0' }}>
                          {c.steps.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ol>
                        <div style={{ color: 'var(--text-muted)' }}>
                          <strong>Expected:</strong> {c.expected_result}
                        </div>
                      </div>
                    </div>
                  ))}
                  {suggestedCases.length === 0 && (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      All generated cases adopted.
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
