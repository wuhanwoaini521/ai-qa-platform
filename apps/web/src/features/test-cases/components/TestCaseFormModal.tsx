import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('testCases');
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleCreateTestCase}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>{t('formTitle')}</h3>
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
                  <label className="form-label">{t('formProject')}</label>
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
                  <label className="form-label">{t('formCaseTitle')}</label>
                  <input
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
                    <label className="form-label">{t('common:priority')}</label>
                    <select
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
                    <label className="form-label">{t('formAutomationStatus')}</label>
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
                  <label className="form-label">{t('formPreconditions')}</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder={t('formPreconditionsPlaceholder')}
                    value={formData.preconditions}
                    onChange={(e) => setFormData({ ...formData, preconditions: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">{t('formSteps')}</label>
                  <textarea
                    rows={4}
                    className="form-control"
                    placeholder={t('formStepsPlaceholder')}
                    value={stepsText}
                    onChange={(e) => setStepsText(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">{t('formExpectedResult')}</label>
                  <textarea
                    rows={2}
                    className="form-control"
                    placeholder={t('formExpectedResultPlaceholder')}
                    value={formData.expected_result}
                    onChange={(e) => setFormData({ ...formData, expected_result: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">{t('formTags')}</label>
                  <input
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
