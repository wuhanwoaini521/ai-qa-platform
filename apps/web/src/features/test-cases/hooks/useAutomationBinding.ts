import { useState } from 'react';
import { api } from '../../../api/client';
import {
  AutomationBinding,
  AutomationBindingStatus,
  AutomationStatus,
  GenerateAutomationResponse,
  TestCase,
} from '../../../types';
import { useCaseHistory } from './useCaseHistory';

export interface BindingFormData {
  file_path: string;
  nodeid: string;
  status: AutomationBindingStatus;
}

interface UseAutomationBindingOptions {
  selectedCase: TestCase | null;
  selectedProjectId: string | null;
  onNavigateToRuns?: (runId?: string) => void;
  updateCaseStatus: (caseId: string, automationStatus: AutomationStatus) => Promise<void>;
}

function errorText(err: unknown): string {
  const message = err instanceof Error ? err.message : undefined;
  return message || String(err);
}

export function useAutomationBinding({
  selectedCase,
  selectedProjectId,
  onNavigateToRuns,
  updateCaseStatus,
}: UseAutomationBindingOptions) {
  const [selectedBinding, setSelectedBinding] = useState<AutomationBinding | null>(null);
  const [isBindingModalOpen, setIsBindingModalOpen] = useState(false);
  const [bindingFormData, setBindingFormData] = useState<BindingFormData>({
    file_path: '',
    nodeid: '',
    status: 'DRAFT',
  });

  const [generatedDraft, setGeneratedDraft] = useState<GenerateAutomationResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [runningCase, setRunningCase] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  const { caseHistory, loadingCaseHistory, fetchCaseHistory, setCaseHistory } = useCaseHistory();

  const fetchBinding = async (caseId: string) => {
    try {
      const binding = await api.getAutomationBinding(caseId);
      setSelectedBinding(binding);
      if (binding) {
        setBindingFormData({
          file_path: binding.file_path,
          nodeid: binding.nodeid,
          status: binding.status,
        });
        if (binding.nodeid && selectedProjectId) {
          fetchCaseHistory(binding.nodeid, selectedProjectId);
        } else {
          setCaseHistory(null);
        }
      } else {
        setBindingFormData({
          file_path: `tests/test_${caseId.slice(0, 8)}.py`,
          nodeid: `tests/test_${caseId.slice(0, 8)}.py::test_${caseId.slice(0, 8)}`,
          status: 'DRAFT',
        });
        setCaseHistory(null);
      }
    } catch (err) {
      console.error('Failed to fetch binding', err);
    }
  };

  const clearBinding = () => setSelectedBinding(null);

  const clearDraft = () => {
    setGeneratedDraft(null);
    setRunMessage(null);
  };

  const handleGenerateAutomation = async () => {
    if (!selectedCase) return;
    try {
      setGenerating(true);
      const draft = await api.generateAutomation(selectedCase.id, true);
      setGeneratedDraft(draft);
    } catch (err) {
      alert(`Generation error: ${errorText(err)}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveDraftToWorkspace = async () => {
    if (!selectedCase || !generatedDraft || !selectedProjectId) return;
    try {
      setSavingDraft(true);
      // Write file into workspace
      await api.writeWorkspaceFile(
        selectedProjectId,
        generatedDraft.target_file,
        generatedDraft.suggested_code
      );
      // Bind to test case
      const nodeid = `${generatedDraft.target_file}::test_${selectedCase.title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/(^_|_$)/g, '')}`;

      const savedBinding = await api.saveAutomationBinding(selectedCase.id, {
        test_case_id: selectedCase.id,
        workspace_id: selectedProjectId,
        nodeid,
        file_path: generatedDraft.target_file,
        status: 'ACTIVE',
      });

      setSelectedBinding(savedBinding);
      await updateCaseStatus(selectedCase.id, 'AUTOMATED');
      alert(`Automation scaffold saved to ${generatedDraft.target_file} and bound to test case.`);
    } catch (err) {
      alert(`Failed to save draft to workspace: ${errorText(err)}`);
    } finally {
      setSavingDraft(false);
    }
  };

  const handleSaveManualBinding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCase) return;
    try {
      const saved = await api.saveAutomationBinding(selectedCase.id, {
        test_case_id: selectedCase.id,
        workspace_id: selectedProjectId || '',
        nodeid: bindingFormData.nodeid,
        file_path: bindingFormData.file_path,
        status: bindingFormData.status,
      });
      setSelectedBinding(saved);
      await updateCaseStatus(selectedCase.id, bindingFormData.status === 'DRAFT' ? 'DRAFT' : 'AUTOMATED');
      setIsBindingModalOpen(false);
    } catch (err) {
      alert(`Binding save error: ${errorText(err)}`);
    }
  };

  const handleRunTestCase = async () => {
    if (!selectedCase || !selectedProjectId || runningCase) return;
    try {
      setRunningCase(true);
      setRunMessage('Triggering execution run...');
      const run = await api.createTestRun({
        project_id: selectedProjectId,
        workspace_id: selectedProjectId,
        nodeids: selectedBinding ? [selectedBinding.nodeid] : [],
        requested_by: `Test Case: ${selectedCase.title}`,
      });
      setRunMessage(`Execution dispatched as Run #${run.id.slice(0, 8)} (${run.status})`);
      if (onNavigateToRuns) {
        setTimeout(() => onNavigateToRuns(run.id), 1200);
      }
    } catch (err) {
      setRunMessage(`Execution error: ${errorText(err)}`);
    } finally {
      setRunningCase(false);
    }
  };

  return {
    selectedBinding,
    bindingFormData,
    setBindingFormData,
    isBindingModalOpen,
    openBindingModal: () => setIsBindingModalOpen(true),
    closeBindingModal: () => setIsBindingModalOpen(false),
    generatedDraft,
    generating,
    savingDraft,
    runningCase,
    runMessage,
    caseHistory,
    loadingCaseHistory,
    fetchBinding,
    clearBinding,
    clearDraft,
    handleGenerateAutomation,
    handleSaveDraftToWorkspace,
    handleSaveManualBinding,
    handleRunTestCase,
  };
}
