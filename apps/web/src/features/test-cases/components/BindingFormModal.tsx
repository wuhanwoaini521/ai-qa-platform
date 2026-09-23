import React from 'react';
import { AutomationStatus } from '../../../types';
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
  return (
    <>
      {isOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleSaveManualBinding}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>Configure Automation Binding</h3>
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
                  <label className="form-label">Test File Path *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. tests/test_checkout.py"
                    value={bindingFormData.test_file_path}
                    onChange={(e) =>
                      setBindingFormData({ ...bindingFormData, test_file_path: e.target.value })
                    }
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Pytest Node ID *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. tests/test_checkout.py::test_coupon_calculation"
                    value={bindingFormData.test_node_id}
                    onChange={(e) =>
                      setBindingFormData({ ...bindingFormData, test_node_id: e.target.value })
                    }
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Automation Status</label>
                  <select
                    className="form-control"
                    value={bindingFormData.status}
                    onChange={(e) =>
                      setBindingFormData({
                        ...bindingFormData,
                        status: e.target.value as AutomationStatus,
                      })
                    }
                  >
                    <option value="MANUAL">MANUAL</option>
                    <option value="DRAFT">DRAFT</option>
                    <option value="AUTOMATED">AUTOMATED</option>
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
                  Save Binding
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
