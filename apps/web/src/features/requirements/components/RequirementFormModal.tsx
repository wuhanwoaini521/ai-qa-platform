import React, { useState } from 'react';
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
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <form onSubmit={handleCreateRequirement}>
              <div className="modal-header">
                <h3>New Requirement</h3>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={onClose}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Project *</label>
                  <select
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
                  <label className="form-label">Title *</label>
                  <input
                    type="text"
                    required
                    className="form-input"
                    placeholder="e.g. User Authentication & Password Reset"
                    value={reqFormData.title}
                    onChange={(e) => setReqFormData({ ...reqFormData, title: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea
                    rows={3}
                    className="form-textarea"
                    placeholder="Detailed explanation of the feature or requirement..."
                    value={reqFormData.description}
                    onChange={(e) => setReqFormData({ ...reqFormData, description: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Acceptance Criteria</label>
                  <textarea
                    rows={3}
                    className="form-textarea"
                    placeholder="Given ..., When ..., Then ..."
                    value={reqFormData.acceptance_criteria}
                    onChange={(e) =>
                      setReqFormData({ ...reqFormData, acceptance_criteria: e.target.value })
                    }
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Initial Status</label>
                  <select
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
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Requirement
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
