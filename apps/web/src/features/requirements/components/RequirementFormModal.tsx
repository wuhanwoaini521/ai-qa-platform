import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Project, RequirementCreate, RequirementStatus } from '../../../types';

interface RequirementFormModalProps {
  isOpen: boolean;
  projects: Project[];
  formData: RequirementCreate;
  setFormData: React.Dispatch<React.SetStateAction<RequirementCreate>>;
  onSubmit: (e: React.FormEvent) => void;
  onClose: () => void;
}

export function useRequirementFormModal(defaultProjectId: string) {
  const [isOpen, setIsOpen] = useState(false);
  const [formData, setFormData] = useState<RequirementCreate>({
    project_id: defaultProjectId,
    title: '',
    description: '',
    acceptance_criteria: '',
    status: 'DRAFT',
  });

  const open = (projectId: string) => {
    setFormData({ ...formData, project_id: projectId });
    setIsOpen(true);
  };

  const close = () => setIsOpen(false);

  const reset = () =>
    setFormData({
      project_id: defaultProjectId,
      title: '',
      description: '',
      acceptance_criteria: '',
      status: 'DRAFT',
    });

  return { isOpen, formData, setFormData, open, close, reset };
}

export const RequirementFormModal: React.FC<RequirementFormModalProps> = ({
  isOpen,
  projects,
  formData: reqFormData,
  setFormData: setReqFormData,
  onSubmit: handleCreateRequirement,
  onClose,
}) => {
  const { t } = useTranslation('requirements');
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="requirement-form-title">
            <form onSubmit={handleCreateRequirement}>
              <div className="modal-header">
                <h3 id="requirement-form-title">{t('requirementFormTitle')}</h3>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  aria-label={t('common:close')}
                  onClick={onClose}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label" htmlFor="requirement-project">{t('requirementFormProjectLabel')}</label>
                  <select
                    id="requirement-project"
                    className="form-select"
                    value={reqFormData.project_id}
                    onChange={(e) => setReqFormData({ ...reqFormData, project_id: e.target.value })}
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="requirement-title">{t('requirementFormTitleLabel')}</label>
                  <input
                    id="requirement-title"
                    type="text"
                    required
                    className="form-input"
                    placeholder={t('requirementFormTitlePlaceholder')}
                    value={reqFormData.title}
                    onChange={(e) => setReqFormData({ ...reqFormData, title: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="requirement-description">{t('common:description')}</label>
                  <textarea
                    id="requirement-description"
                    rows={3}
                    className="form-textarea"
                    placeholder={t('requirementFormDescriptionPlaceholder')}
                    value={reqFormData.description}
                    onChange={(e) => setReqFormData({ ...reqFormData, description: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="requirement-acceptance-criteria">{t('requirementFormAcceptanceCriteriaLabel')}</label>
                  <textarea
                    id="requirement-acceptance-criteria"
                    rows={3}
                    className="form-textarea"
                    placeholder={t('requirementFormAcceptanceCriteriaPlaceholder')}
                    value={reqFormData.acceptance_criteria}
                    onChange={(e) =>
                      setReqFormData({ ...reqFormData, acceptance_criteria: e.target.value })
                    }
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="requirement-status">{t('requirementFormInitialStatusLabel')}</label>
                  <select
                    id="requirement-status"
                    className="form-select"
                    value={reqFormData.status}
                    onChange={(e) =>
                      setReqFormData({ ...reqFormData, status: e.target.value as RequirementStatus })
                    }
                  >
                    <option value="DRAFT">DRAFT</option>
                    <option value="READY">READY</option>
                    <option value="ARCHIVED">ARCHIVED</option>
                  </select>
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
                  {t('requirementFormSubmit')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
