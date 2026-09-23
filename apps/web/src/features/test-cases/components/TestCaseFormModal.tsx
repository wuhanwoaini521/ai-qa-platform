import React, { useState } from 'react';
import { AutomationStatus, Project, TestCaseCreate, TestCasePriority } from '../../../types';

interface TestCaseFormModalProps {
  isOpen: boolean;
  projects: Project[];
  formData: TestCaseCreate;
  setFormData: React.Dispatch<React.SetStateAction<TestCaseCreate>>;
  stepsText: string;
  setStepsText: React.Dispatch<React.SetStateAction<string>>;
  tagsText: string;
  setTagsText: React.Dispatch<React.SetStateAction<string>>;
  onSubmit: (e: React.FormEvent) => void;
  onClose: () => void;
}

export function useTestCaseFormModal(defaultProjectId: string) {
  const [isOpen, setIsOpen] = useState(false);
  const [formData, setFormData] = useState<TestCaseCreate>({
    project_id: defaultProjectId,
    title: '',
    preconditions: '',
    steps: [],
    expected_result: '',
    priority: 'P1',
    automation_status: 'MANUAL',
    tags: [],
  });
  const [stepsText, setStepsText] = useState('');
  const [tagsText, setTagsText] = useState('');

  const open = (projectId: string) => {
    setFormData({ ...formData, project_id: projectId });
    setIsOpen(true);
  };

  const close = () => setIsOpen(false);

  const reset = () => {
    setFormData({
      project_id: defaultProjectId,
      title: '',
      preconditions: '',
      steps: [],
      expected_result: '',
      priority: 'P1',
      automation_status: 'MANUAL',
      tags: [],
    });
    setStepsText('');
    setTagsText('');
  };

  return {
    isOpen,
    formData,
    setFormData,
    stepsText,
    setStepsText,
    tagsText,
    setTagsText,
    open,
    close,
    reset,
  };
}

export const TestCaseFormModal: React.FC<TestCaseFormModalProps> = ({
  isOpen,
  projects,
  formData,
  setFormData,
  stepsText,
  setStepsText,
  tagsText,
  setTagsText,
  onSubmit: handleCreateTestCase,
  onClose,
}) => {
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleCreateTestCase}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>New Test Case</h3>
                <button
                  type="button"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  onClick={onClose}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label">Project *</label>
                  <select
                    className="form-control"
                    value={formData.project_id}
                    onChange={(e) => setFormData({ ...formData, project_id: e.target.value })}
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Test Case Title *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. Verify checkout calculation with 10% coupon"
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">Priority</label>
                    <select
                      className="form-control"
                      value={formData.priority}
                      onChange={(e) =>
                        setFormData({ ...formData, priority: e.target.value as TestCasePriority })
                      }
                    >
                      <option value="P0">P0 - Blocker</option>
                      <option value="P1">P1 - Critical</option>
                      <option value="P2">P2 - Major</option>
                      <option value="P3">P3 - Minor</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Automation Status</label>
                    <select
                      className="form-control"
                      value={formData.automation_status}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          automation_status: e.target.value as AutomationStatus,
                        })
                      }
                    >
                      <option value="MANUAL">MANUAL</option>
                      <option value="DRAFT">DRAFT</option>
                      <option value="AUTOMATED">AUTOMATED</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Preconditions</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. User is logged in as standard customer..."
                    value={formData.preconditions}
                    onChange={(e) => setFormData({ ...formData, preconditions: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Steps (One step per line)</label>
                  <textarea
                    rows={4}
                    className="form-control"
                    placeholder="1. Open product page&#10;2. Click Add to Cart&#10;3. Navigate to checkout"
                    value={stepsText}
                    onChange={(e) => setStepsText(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Expected Result</label>
                  <textarea
                    rows={2}
                    className="form-control"
                    placeholder="Final total is reduced by exactly 10%."
                    value={formData.expected_result}
                    onChange={(e) => setFormData({ ...formData, expected_result: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Tags (comma separated)</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="smoke, checkout, cart"
                    value={tagsText}
                    onChange={(e) => setTagsText(e.target.value)}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={onClose}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Test Case
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
