import React from 'react';
import { Plus } from 'lucide-react';
import { Project, TestCase } from '../../types';
import { useTestCases } from './hooks/useTestCases';
import { useAutomationBinding } from './hooks/useAutomationBinding';
import { TestCaseList } from './components/TestCaseList';
import { TestCaseDetail } from './components/TestCaseDetail';
import { AutomationBindingPanel } from './components/AutomationBindingPanel';
import { CaseExecutionHistoryPanel } from './components/CaseExecutionHistoryPanel';
import { BindingFormModal } from './components/BindingFormModal';
import { TestCaseFormModal, useTestCaseFormModal } from './components/TestCaseFormModal';

interface TestCasesPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onNavigateToStudio?: (filePath: string) => void;
  onNavigateToRuns?: (runId?: string) => void;
  initialTestCaseId?: string | null;
  onSelectTestCase?: (testCaseId: string) => void;
}

export const TestCasesPage: React.FC<TestCasesPageProps> = ({
  projects,
  selectedProjectId,
  onNavigateToStudio,
  onNavigateToRuns,
  initialTestCaseId,
  onSelectTestCase,
}) => {
  const form = useTestCaseFormModal(selectedProjectId || (projects[0]?.id ?? ''));

  // `binding` is only dereferenced once the case list loads, after both hooks are initialized.
  const cases = useTestCases({
    selectedProjectId,
    projects,
    initialTestCaseId,
    onCaseSelected: (caseId) => binding.fetchBinding(caseId),
    onCaseListEmpty: () => binding.clearBinding(),
  });
  const binding = useAutomationBinding({
    selectedCase: cases.selectedCase,
    selectedProjectId,
    onNavigateToRuns,
    updateCaseStatus: cases.updateStatus,
  });

  const { selectedCase } = cases;

  const handleSelectCase = (tc: TestCase) => {
    cases.setSelectedCase(tc);
    binding.clearDraft();
    binding.fetchBinding(tc.id);
    onSelectTestCase?.(tc.id);
  };

  const handleCreateTestCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.formData.title.trim()) return;

    const parsedSteps = form.stepsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    const parsedTags = form.tagsText
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const created = await cases.createTestCase({
      ...form.formData,
      steps: parsedSteps,
      tags: parsedTags,
    });
    if (!created) return;
    form.close();
    form.reset();
    binding.fetchBinding(created.id);
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Test Case & Automation Binding</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Manage test cases, generate AI Playwright code, and link business tests to executable pytest node IDs.
          </p>
        </div>
        <button
          className="btn btn-primary"
          disabled={projects.length === 0}
          onClick={() => form.open(selectedProjectId || projects[0]?.id || '')}
        >
          <Plus size={16} /> New Test Case
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card">
          <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Please create a project first before adding test cases.
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1.8fr', gap: '20px' }}>
          <TestCaseList
            testCases={cases.testCases}
            loading={cases.loading}
            selectedCase={selectedCase}
            onSelect={handleSelectCase}
          />

          {selectedCase ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <TestCaseDetail selectedCase={selectedCase} onUpdateStatus={cases.updateStatus} />

              <AutomationBindingPanel
                selectedBinding={binding.selectedBinding}
                generatedDraft={binding.generatedDraft}
                savingDraft={binding.savingDraft}
                runningCase={binding.runningCase}
                generating={binding.generating}
                runMessage={binding.runMessage}
                onNavigateToStudio={onNavigateToStudio}
                onOpenBindingModal={binding.openBindingModal}
                onRunTestCase={binding.handleRunTestCase}
                onGenerateAutomation={binding.handleGenerateAutomation}
                onSaveDraftToWorkspace={binding.handleSaveDraftToWorkspace}
              />

              {binding.selectedBinding && (
                <CaseExecutionHistoryPanel
                  caseHistory={binding.caseHistory}
                  loadingCaseHistory={binding.loadingCaseHistory}
                />
              )}
            </div>
          ) : (
            <div className="card">
              <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Select a test case to view step details and automation bindings.
              </div>
            </div>
          )}
        </div>
      )}

      <BindingFormModal
        isOpen={binding.isBindingModalOpen}
        formData={binding.bindingFormData}
        setFormData={binding.setBindingFormData}
        onSubmit={binding.handleSaveManualBinding}
        onClose={binding.closeBindingModal}
      />

      <TestCaseFormModal
        isOpen={form.isOpen}
        projects={projects}
        formData={form.formData}
        setFormData={form.setFormData}
        stepsText={form.stepsText}
        setStepsText={form.setStepsText}
        tagsText={form.tagsText}
        setTagsText={form.setTagsText}
        onSubmit={handleCreateTestCase}
        onClose={form.close}
      />
    </div>
  );
};
