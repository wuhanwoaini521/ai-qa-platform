import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { TestDesignCategory, TestDesignCreate } from '../../../types';

interface TestDesignFormModalProps {
  isOpen: boolean;
  formData: TestDesignCreate;
  setFormData: React.Dispatch<React.SetStateAction<TestDesignCreate>>;
  onSubmit: (e: React.FormEvent) => void;
  onClose: () => void;
}

export function useTestDesignFormModal() {
  const [isOpen, setIsOpen] = useState(false);
  const [formData, setFormData] = useState<TestDesignCreate>({
    requirement_id: '',
    title: '',
    category: 'FUNCTIONAL',
    description: '',
    risk: 'Medium',
    status: 'DRAFT',
  });

  const open = (requirementId: string) => {
    setFormData({ ...formData, requirement_id: requirementId });
    setIsOpen(true);
  };

  const close = () => setIsOpen(false);

  const reset = () =>
    setFormData({
      requirement_id: '',
      title: '',
      category: 'FUNCTIONAL',
      description: '',
      risk: 'Medium',
      status: 'DRAFT',
    });

  return { isOpen, formData, setFormData, open, close, reset };
}

export const TestDesignFormModal: React.FC<TestDesignFormModalProps> = ({
  isOpen,
  formData: designFormData,
  setFormData: setDesignFormData,
  onSubmit: handleCreateTestDesign,
  onClose,
}) => {
  const { t } = useTranslation('requirements');
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <form onSubmit={handleCreateTestDesign}>
              <div className="modal-header">
                <h3>{t('designFormTitle')}</h3>
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
                  <label className="form-label">{t('designFormTitleLabel')}</label>
                  <input
                    type="text"
                    required
                    className="form-input"
                    placeholder={t('designFormTitlePlaceholder')}
                    value={designFormData.title}
                    onChange={(e) => setDesignFormData({ ...designFormData, title: e.target.value })}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">{t('designFormCategoryLabel')}</label>
                    <select
                      className="form-select"
                      value={designFormData.category}
                      onChange={(e) =>
                        setDesignFormData({
                          ...designFormData,
                          category: e.target.value as TestDesignCategory,
                        })
                      }
                    >
                      <option value="FUNCTIONAL">FUNCTIONAL</option>
                      <option value="BOUNDARY">BOUNDARY</option>
                      <option value="NEGATIVE">NEGATIVE</option>
                      <option value="ANALYTICS">ANALYTICS</option>
                      <option value="API">API</option>
                      <option value="UI">UI</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('designFormRiskLabel')}</label>
                    <select
                      className="form-select"
                      value={designFormData.risk}
                      onChange={(e) => setDesignFormData({ ...designFormData, risk: e.target.value })}
                    >
                      <option value="Low">Low</option>
                      <option value="Medium">Medium</option>
                      <option value="High">High</option>
                      <option value="Critical">Critical</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">{t('designFormDetailsLabel')}</label>
                  <textarea
                    rows={3}
                    className="form-textarea"
                    placeholder={t('designFormDetailsPlaceholder')}
                    value={designFormData.description}
                    onChange={(e) =>
                      setDesignFormData({ ...designFormData, description: e.target.value })
                    }
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
                  {t('designFormSubmit')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
