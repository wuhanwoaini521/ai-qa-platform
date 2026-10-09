import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AutomationStatus, Project, TestCaseCreate, TestCasePriority } from '../../../types';

interface TestCaseFormModalProps {
  isOpen: boolean;
  projects: Project[];
  workspaceMode?: boolean;
  formData: TestCaseCreate;
  setFormData: React.Dispatch<React.SetStateAction<TestCaseCreate>>;
  stepsText: string;
  setStepsText: React.Dispatch<React.SetStateAction<string>>;
  tagsText: string;
  setTagsText: React.Dispatch<React.SetStateAction<string>>;
  onSubmit: (e: React.FormEvent) => void;
  onClose: () => void;
}

export function useTestCaseFormModal(
  defaultProjectId: string,
  initialRequirementId?: string | null,
) {
  const [isOpen, setIsOpen] = useState(false);
  const [formData, setFormData] = useState<TestCaseCreate>({
    project_id: defaultProjectId,
    requirement_id: initialRequirementId,
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
    setFormData({
      project_id: projectId,
      requirement_id: initialRequirementId,
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
    setIsOpen(true);
  };

  const close = () => setIsOpen(false);

  const reset = () => {
    setFormData({
      project_id: defaultProjectId,
      requirement_id: initialRequirementId,
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
  workspaceMode = false,
  formData,
  setFormData,
  stepsText,
  setStepsText,
  tagsText,
  setTagsText,
  onSubmit: handleCreateTestCase,
  onClose,
}) => {
  const { t } = useTranslation('testCases');
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="test-case-form-title">
            <form onSubmit={handleCreateTestCase}>
              <div className="modal-header">
                <h3 id="test-case-form-title" style={{ fontSize: '15px', fontWeight: 700 }}>{t('formTitle')}</h3>
                <button
                  type="button"
                  aria-label={t('common:close')}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  onClick={onClose}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="test-case-project">{t('formProject')}</label>
                  <select
                    id="test-case-project"
                    className="form-control"
                    disabled={workspaceMode}
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
                  <label className="form-label" htmlFor="test-case-title">{t('formCaseTitle')}</label>
                  <input
                    id="test-case-title"
                    type="text"
                    required
                    className="form-control"
                    placeholder={t('formCaseTitlePlaceholder')}
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="test-case-priority">{t('common:priority')}</label>
                    <select
                      id="test-case-priority"
                      className="form-control"
                      value={formData.priority}
                      onChange={(e) =>
                        setFormData({ ...formData, priority: e.target.value as TestCasePriority })
                      }
                    >
                      <option value="P0">{t('formPriorityP0')}</option>
                      <option value="P1">{t('formPriorityP1')}</option>
                      <option value="P2">{t('formPriorityP2')}</option>
                      <option value="P3">{t('formPriorityP3')}</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="test-case-automation-status">{t('formAutomationStatus')}</label>
                    <select
                      id="test-case-automation-status"
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
                  <label className="form-label" htmlFor="test-case-preconditions">{t('formPreconditions')}</label>
                  <input
                    id="test-case-preconditions"
                    type="text"
                    className="form-control"
                    placeholder={t('formPreconditionsPlaceholder')}
                    value={formData.preconditions}
                    onChange={(e) => setFormData({ ...formData, preconditions: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="test-case-steps">{t('formSteps')}</label>
                  <textarea
                    id="test-case-steps"
                    rows={4}
                    className="form-control"
                    placeholder={t('formStepsPlaceholder')}
                    value={stepsText}
                    onChange={(e) => setStepsText(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="test-case-expected-result">{t('formExpectedResult')}</label>
                  <textarea
                    id="test-case-expected-result"
                    rows={2}
                    className="form-control"
                    placeholder={t('formExpectedResultPlaceholder')}
                    value={formData.expected_result}
                    onChange={(e) => setFormData({ ...formData, expected_result: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="test-case-tags">{t('formTags')}</label>
                  <input
                    id="test-case-tags"
                    type="text"
                    className="form-control"
                    placeholder={t('formTagsPlaceholder')}
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
                  {t('common:cancel')}
                </button>
                <button type="submit" className="btn btn-primary">
                  {t('formSave')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
