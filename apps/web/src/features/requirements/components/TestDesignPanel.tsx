import React from 'react';
import { useTranslation } from 'react-i18next';
import { Layers, ListChecks, Plus, Sparkles } from 'lucide-react';
import { TestDesign } from '../../../types';

interface TestDesignPanelProps {
  testDesigns: TestDesign[];
  onGenerateDesigns: () => void;
  onAddManualDesign: () => void;
  onGenerateCases: (design: TestDesign) => void;
}

export const TestDesignPanel: React.FC<TestDesignPanelProps> = ({
  testDesigns,
  onGenerateDesigns,
  onAddManualDesign,
  onGenerateCases,
}) => {
  const { t } = useTranslation('requirements');
  return (
    <div className="card">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Layers size={16} color="#16a34a" />
          <span className="card-title">{t('designsTitle', { total: testDesigns.length })}</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-primary btn-sm" onClick={onGenerateDesigns}>
            <Sparkles size={13} />
            <span>{t('designsGenerateDesigns')}</span>
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={onAddManualDesign}
          >
            <Plus size={13} /> {t('designsAddManual')}
          </button>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {testDesigns.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            {t('designsEmptyBefore')}<strong>{t('designsEmptyAction')}</strong>{t('designsEmptyAfter')}
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('designsColumnTitle')}</th>
                <th>{t('designsColumnCategory')}</th>
                <th>{t('designsColumnRisk')}</th>
                <th>{t('common:status')}</th>
                <th>{t('common:actions')}</th>
              </tr>
            </thead>
            <tbody>
              {testDesigns.map((td) => (
                <tr key={td.id}>
                  <td style={{ fontWeight: 500 }}>{td.title}</td>
                  <td>
                    <span className="status-pill status-pill-draft">{td.category}</span>
                  </td>
                  <td>{td.risk}</td>
                  <td>
                    <span className="status-pill status-pill-passed">{td.status}</span>
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => onGenerateCases(td)}
                    >
                      <ListChecks size={12} />
                      <span>{t('designsGenerateCases')}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
