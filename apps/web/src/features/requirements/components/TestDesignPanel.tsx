import React from 'react';
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
  return (
    <div className="card">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Layers size={16} color="#16a34a" />
          <span className="card-title">Test Designs ({testDesigns.length})</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-primary btn-sm" onClick={onGenerateDesigns}>
            <Sparkles size={13} />
            <span>AI Generate Designs</span>
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={onAddManualDesign}
          >
            <Plus size={13} /> Add Manual Design
          </button>
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {testDesigns.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            No test designs yet. Click <strong>AI Generate Designs</strong> to produce structured functional, boundary, and negative dimensions.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Design Title</th>
                <th>Category</th>
                <th>Risk</th>
                <th>Status</th>
                <th>Actions</th>
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
                      <span>AI Generate Cases</span>
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
