import React from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import {
  ContextTaskProgress,
  useContextTask,
} from '../../components/ContextTaskProgress';
import { Project, TestCase } from '../../types';
import { useTestCases } from './hooks/useTestCases';
import { useAutomationBinding } from './hooks/useAutomationBinding';
import { TestCaseList } from './components/TestCaseList';
import { TestCaseDetail } from './components/TestCaseDetail';
import { AutomationBindingPanel } from './components/AutomationBindingPanel';
import { CaseExecutionHistoryPanel } from './components/CaseExecutionHistoryPanel';
import { BindingFormModal } from './components/BindingFormModal';
import {
  TestCaseFormModal,
  useTestCaseFormModal,
} from './components/TestCaseFormModal';

interface TestCasesPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onNavigateToStudio?: (filePath: string) => void;
  onNavigateToRuns?: (runId?: string) => void;
  initialTestCaseId?: string | null;
  initialRequirementId?: string | null;
  onSelectTestCase?: (testCaseId: string) => void;
  onTaskStarted?: (taskId: string) => void;
  workspaceMode?: boolean;
  focusAutomation?: boolean;
  hideRunAction?: boolean;
  onCaseCreated?: (testCase: TestCase) => void;
}

export const TestCasesPage: React.FC<TestCasesPageProps> = ({
  projects,
  selectedProjectId,
  onNavigateToStudio,
  onNavigateToRuns,
  initialTestCaseId,
  initialRequirementId,
  onSelectTestCase,
  onTaskStarted,
  workspaceMode = false,
  focusAutomation = false,
  hideRunAction = false,
  onCaseCreated,
}) => {
  const { t } = useTranslation('testCases');
  const form = useTestCaseFormModal(
    selectedProjectId || (projects[0]?.id ?? ''),
    initialRequirementId,
  );

  // `binding` is only dereferenced once the case list loads, after both hooks are initialized.
  const cases = useTestCases({
    selectedProjectId,
    projects,
    initialTestCaseId,
    emptySelectionWhenUnmatched: workspaceMode,
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
  const caseTask = useContextTask(
    selectedCase?.project_id ?? null,
    'test_case',
    selectedCase?.id ?? null,
  );

  const startCaseTask = async (
    type: 'CREATE_TEST' | 'OPTIMIZE_TEST' | 'REVIEW_TEST',
  ) => {
    const target = binding.selectedBinding;
    if (!selectedCase || (!target && type !== 'CREATE_TEST')) return;
    const created = await caseTask.start({
      type,
      goal:
        type === 'CREATE_TEST'
          ? `${selectedCase.title}: ${selectedCase.expected_result}`
          : t(
              type === 'OPTIMIZE_TEST'
                ? 'tasks:optimizeGoal'
                : 'tasks:reviewGoal',
              { title: selectedCase.title },
            ),
      project_id: selectedCase.project_id,
      workspace_id: target?.workspace_id || selectedCase.project_id,
      inputs: {
        test_case_id: selectedCase.id,
        ...(type === 'CREATE_TEST'
          ? {
              case_name: selectedCase.title,
              requirement: selectedCase.expected_result,
            }
          : { file_path: target?.file_path, test_nodeid: target?.nodeid }),
      },
    });
    if (created) onTaskStarted?.(created.id);
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
    if (onCaseCreated) onCaseCreated(created);
    else onSelectTestCase?.(created.id);
  };

  const automationBindingPanel = <AutomationBindingPanel
    progressEvents={binding.progress.events}
    progressError={binding.progress.error}
    selectedBinding={binding.selectedBinding}
    generatedDraft={binding.generatedDraft}
    savingDraft={binding.savingDraft}
    runningCase={binding.runningCase}
    generating={binding.generating}
    hideRunAction={hideRunAction}
    runMessage={binding.runMessage}
    onNavigateToStudio={onNavigateToStudio}
    onOpenBindingModal={binding.openBindingModal}
    onRunTestCase={binding.handleRunTestCase}
    onGenerateAutomation={binding.handleGenerateAutomation}
    onSaveDraftToWorkspace={binding.handleSaveDraftToWorkspace}
  />;

  return (
    <div className={`page-container test-cases-page${workspaceMode ? ' workspace-cases-embedded' : ''}${focusAutomation ? ' is-automation-focus' : ''}`}>
      {workspaceMode ? <div className="workspace-case-toolbar">
        <span>{t('pageTitle')}</span>
        <button
          className="btn btn-primary btn-sm"
          disabled={projects.length === 0}
          onClick={() => form.open(selectedProjectId || projects[0]?.id || '')}
        >
          <Plus size={14} /> {t('newTestCase')}
        </button>
      </div> : <div className="page-header">
        <div>
          <h2>{t('pageTitle')}</h2>
          <p className="subtitle">{t('pageSubtitle')}</p>
        </div>
        <button
          className="btn btn-primary"
          disabled={projects.length === 0}
          onClick={() => form.open(selectedProjectId || projects[0]?.id || '')}
        >
          <Plus size={16} /> {t('newTestCase')}
        </button>
      </div>}

      {projects.length === 0 ? (
        <div className="card">
          <div
            className="card-body"
            style={{
              padding: '40px',
              textAlign: 'center',
              color: 'var(--text-muted)',
            }}
          >
            {t('createProjectFirst')}
          </div>
        </div>
      ) : (
        <div className="test-cases-grid">
          {!workspaceMode && <TestCaseList
            testCases={cases.testCases}
            loading={cases.loading}
            selectedCase={selectedCase}
            onSelect={handleSelectCase}
          />}

          {selectedCase ? (
            <div className="test-case-workspace">
              <TestCaseDetail
                selectedCase={selectedCase}
                onUpdateStatus={cases.updateStatus}
                aiDisabled={!binding.selectedBinding || caseTask.busy}
                onOptimize={() => startCaseTask('OPTIMIZE_TEST')}
                onReview={() => startCaseTask('REVIEW_TEST')}
                onCopilot={() => startCaseTask('CREATE_TEST')}
                copilotDisabled={caseTask.busy}
              />
              <ContextTaskProgress
                task={caseTask.task}
                error={caseTask.error}
              />
              {workspaceMode ? <details className="workspace-case-automation" open={binding.generating || Boolean(binding.progress.error || binding.generatedDraft)}>
                <summary><span>{t('bindingTitle')}</span><small>{binding.selectedBinding?.file_path ?? t('bindingConfigure')}</small></summary>
                {automationBindingPanel}
              </details> : automationBindingPanel}

              {binding.selectedBinding && (
                <CaseExecutionHistoryPanel
                  caseHistory={binding.caseHistory}
                  loadingCaseHistory={binding.loadingCaseHistory}
                />
              )}
            </div>
          ) : (
            <div className="card">
              <div
                className="card-body"
                style={{
                  padding: '40px',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                }}
              >
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
        workspaceMode={workspaceMode}
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
