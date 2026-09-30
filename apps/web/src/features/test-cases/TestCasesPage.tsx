import React from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import { ContextTaskProgress, useContextTask } from '../../components/ContextTaskProgress';
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
  const { t } = useTranslation('testCases');
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
  const caseTask = useContextTask(selectedCase?.project_id ?? null, 'test_case', selectedCase?.id ?? null);

  const startCaseTask = (type: 'OPTIMIZE_TEST' | 'REVIEW_TEST') => {
    const target = binding.selectedBinding;
    if (!selectedCase || !target) return;
    void caseTask.start({
      type,
      goal: t(type === 'OPTIMIZE_TEST' ? 'tasks:optimizeGoal' : 'tasks:reviewGoal', { title: selectedCase.title }),
      project_id: selectedCase.project_id,
      workspace_id: target.workspace_id || selectedCase.project_id,
      inputs: { test_case_id: selectedCase.id, file_path: target.file_path, test_nodeid: target.nodeid },
    });
  };

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
    <div className="page-container test-cases-page">
      <div className="page-header">
        <div>
          <h2>{t('pageTitle')}</h2>
          <p className="subtitle">
            {t('pageSubtitle')}
          </p>
        </div>
        <button
          className="btn btn-primary"
          disabled={projects.length === 0}
          onClick={() => form.open(selectedProjectId || projects[0]?.id || '')}
        >
          <Plus size={16} /> {t('newTestCase')}
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card">
          <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {t('createProjectFirst')}
          </div>
        </div>
      ) : (
        <div className="test-cases-grid">
          <TestCaseList
            testCases={cases.testCases}
            loading={cases.loading}
            selectedCase={selectedCase}
            onSelect={handleSelectCase}
          />

          {selectedCase ? (
            <div className="test-case-workspace">
              <TestCaseDetail selectedCase={selectedCase} onUpdateStatus={cases.updateStatus} aiDisabled={!binding.selectedBinding || caseTask.busy} onOptimize={() => startCaseTask('OPTIMIZE_TEST')} onReview={() => startCaseTask('REVIEW_TEST')} />
              <ContextTaskProgress task={caseTask.task} error={caseTask.error} />

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
                {t('selectCase')}
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
