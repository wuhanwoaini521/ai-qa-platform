import React from 'react';
import { useTranslation } from 'react-i18next';
import { AutomationBindingStatus } from '../../../types';
import { BindingFormData } from '../hooks/useAutomationBinding';

interface BindingFormModalProps {
  isOpen: boolean;
  formData: BindingFormData;
  setFormData: React.Dispatch<React.SetStateAction<BindingFormData>>;
  onSubmit: (e: React.FormEvent) => void;
  onClose: () => void;
}

export const BindingFormModal: React.FC<BindingFormModalProps> = ({
  isOpen,
  formData: bindingFormData,
  setFormData: setBindingFormData,
  onSubmit: handleSaveManualBinding,
  onClose,
}) => {
  const { t } = useTranslation('testCases');
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleSaveManualBinding}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>{t('bindingModalTitle')}</h3>
                <button
                  type="button"
                  style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                  onClick={onClose}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label">{t('bindingModalFilePath')}</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. tests/test_checkout.py"
                    value={bindingFormData.file_path}
                    onChange={(e) =>
                      setBindingFormData({ ...bindingFormData, file_path: e.target.value })
                    }
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{t('bindingModalNodeId')}</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. tests/test_checkout.py::test_coupon_calculation"
                    value={bindingFormData.nodeid}
                    onChange={(e) =>
                      setBindingFormData({ ...bindingFormData, nodeid: e.target.value })
                    }
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{t('bindingModalStatus')}</label>
                  <select
                    className="form-control"
                    value={bindingFormData.status}
                    onChange={(e) =>
                      setBindingFormData({
                        ...bindingFormData,
                        status: e.target.value as AutomationBindingStatus,
                      })
                    }
                  >
                    <option value="DRAFT">DRAFT</option>
                    <option value="VALIDATED">VALIDATED</option>
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="BROKEN">BROKEN</option>
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
                  {t('bindingModalSave')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
