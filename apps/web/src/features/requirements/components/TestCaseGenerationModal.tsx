import React from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('requirements');
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '750px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="var(--color-primary)" />
                <div>
                  <h3>{t('caseModalTitle')}</h3>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {t('caseModalDesign', { title: activeDesignForCases?.title })}
                  </div>
                </div>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={onClose}>
                {t('common:close')}
              </button>
            </div>
            <div className="modal-body">
              {generatingCases ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <RefreshCw size={24} className="spinning" style={{ marginBottom: '0.75rem' }} />
                  <div>{t('caseModalGenerating')}</div>
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
                            {t('caseModalPriority')} <strong>{c.priority}</strong> | {t('caseModalTags')} {c.tags.join(', ')}
                          </div>
                        </div>
                        <button className="btn btn-primary btn-sm" onClick={() => handleAdoptCase(c)}>
                          {t('caseModalAdopt')}
                        </button>
                      </div>
                      <div style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>
                        <div style={{ fontWeight: 500 }}>{t('caseModalSteps')}</div>
                        <ol style={{ paddingLeft: '1.25rem', margin: '0.25rem 0' }}>
                          {c.steps.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ol>
                        <div style={{ color: 'var(--text-muted)' }}>
                          <strong>{t('caseModalExpected')}</strong> {c.expected_result}
                        </div>
                      </div>
                    </div>
                  ))}
                  {suggestedCases.length === 0 && (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      {t('caseModalEmpty')}
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
