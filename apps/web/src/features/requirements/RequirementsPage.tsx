import React from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Project, Requirement } from '../../types';
import { useRequirements } from './hooks/useRequirements';
import { buildRequirementSelectionModel } from './requirementSelectionModel';
import { useTestDesigns } from './hooks/useTestDesigns';
import { useRequirementAI } from './hooks/useRequirementAI';
import { useJiraImport } from './hooks/useJiraImport';
import { RequirementToolbar } from './components/RequirementToolbar';
import { RequirementList } from './components/RequirementList';
import { RequirementLifecyclePanel } from '../lifecycle/RequirementLifecyclePanel';
import { api } from '../../api/client';
import { TestDesignPanel } from './components/TestDesignPanel';
import { RequirementAnalysisModal } from './components/RequirementAnalysisModal';
import { TestDesignGenerationModal } from './components/TestDesignGenerationModal';
import { TestCaseGenerationModal } from './components/TestCaseGenerationModal';
import {
  RequirementFormModal,
  useRequirementFormModal,
} from './components/RequirementFormModal';
import {
  TestDesignFormModal,
  useTestDesignFormModal,
} from './components/TestDesignFormModal';
import { JiraImportModal } from './components/JiraImportModal';

interface RequirementsPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onNavigateToStudio?: (filePath: string) => void;
  initialRequirementId?: string | null;
  onSelectRequirement?: (requirementId: string) => void;
  onCaseCreated?: (testCaseId: string, testDesignId?: string) => void;
  onStartAnalysis?: (requirement: Requirement) => Promise<void>;
  analysisRunning?: boolean;
  analysisRefreshVersion?: number | null;
  onRequirementChanged?: (requirement: Requirement) => void;
  workspaceMode?: boolean;
}

export const RequirementsPage: React.FC<RequirementsPageProps> = ({
  projects,
  selectedProjectId,
  initialRequirementId,
  onSelectRequirement,
  onCaseCreated,
  onStartAnalysis,
  analysisRunning = false,
  analysisRefreshVersion = null,
  onRequirementChanged,
  workspaceMode = false,
}) => {
  const { t } = useTranslation('requirements');
  const [searchParams, setSearchParams] = useSearchParams();
  const [analysisStartError, setAnalysisStartError] = React.useState('');
  const reqForm = useRequirementFormModal(
    selectedProjectId || (projects[0]?.id ?? ''),
  );
  const designForm = useTestDesignFormModal();

  const reqs = useRequirements({
    selectedProjectId,
    projects,
    initialRequirementId,
  });
  const designs = useTestDesigns(reqs.selectedReq);
  const ai = useRequirementAI({
    selectedReq: reqs.selectedReq,
    onDesignCreated: designs.appendDesign,
    onCaseCreated,
  });
  const jira = useJiraImport({
    selectedProjectId,
    projects,
    onImported: reqs.addImported,
  });

  const { selectedReq } = reqs;
  const requirementSelection = buildRequirementSelectionModel(reqs.requirements, selectedReq);

  const handleWorkspaceAnalysis = async () => {
    if (!selectedReq || !onStartAnalysis || analysisRunning) return;
    setAnalysisStartError('');
    setSearchParams({ ...Object.fromEntries(searchParams), tab: 'analysis' });
    try {
      await onStartAnalysis(selectedReq);
    } catch (reason) {
      setAnalysisStartError(String(reason));
    }
  };

  React.useEffect(() => {
    if (!workspaceMode || analysisRefreshVersion == null || analysisRefreshVersion <= 0 || !selectedReq) return;
    let active = true;
    void api.getRequirement(selectedReq.id).then((item) => {
      if (!active) return;
      reqs.setSelectedReq(item);
      onRequirementChanged?.(item);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [analysisRefreshVersion, onRequirementChanged, reqs.setSelectedReq, selectedReq?.id, workspaceMode]);

  const handleSelectRequirement = (requirement: Requirement) => {
    reqs.setSelectedReq(requirement);
    onSelectRequirement?.(requirement.id);
  };

  const handleCreateRequirement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reqForm.formData.title.trim()) return;
    const created = await reqs.createRequirement(reqForm.formData);
    if (!created) return;
    onRequirementChanged?.(created);
    onSelectRequirement?.(created.id);
    reqForm.close();
    reqForm.reset();
  };

  const handleCreateTestDesign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedReq || !designForm.formData.title.trim()) return;
    const created = await designs.createDesign({
      ...designForm.formData,
      requirement_id: selectedReq.id,
    });
    if (!created) return;
    designForm.close();
    designForm.reset();
  };

  return (
    <div className={workspaceMode ? 'workspace-requirement-embedded' : undefined}>
      <div className={workspaceMode ? 'workspace-requirement-toolbar' : undefined}>
        {workspaceMode && requirementSelection && (
          <div className="workspace-requirement-selection">
            <span className="workspace-requirement-selection-label">{t('currentRequirement')}</span>
            {requirementSelection.kind === 'multiple' ? (
              <select
                className="form-select workspace-requirement-selection-control"
                aria-label={t('currentRequirement')}
                value={requirementSelection.selectedId}
                onChange={(event) => {
                  const requirement = reqs.requirements.find((item) => item.id === event.target.value);
                  if (requirement) handleSelectRequirement(requirement);
                }}
              >
                {requirementSelection.options.map((option) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
            ) : (
              <div className="workspace-requirement-selection-current">
                <strong>{requirementSelection.displayId}</strong>
                <span>{requirementSelection.title}</span>
              </div>
            )}
          </div>
        )}
        <RequirementToolbar
          projects={projects}
          onOpenJira={jira.handleOpenJiraModal}
          onNewRequirement={() =>
            reqForm.open(selectedProjectId || projects[0]?.id || '')
          }
          onAnalyze={workspaceMode && selectedReq ? handleWorkspaceAnalysis : undefined}
          analysisRunning={analysisRunning}
        />
      </div>
      {analysisStartError && <div className="workspace-error" role="alert">{analysisStartError}</div>}

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
            {t('pageNoProject')}
          </div>
        </div>
      ) : workspaceMode ? (
          selectedReq ? (
            <div className="workspace-requirement-detail">
              <RequirementLifecyclePanel
                key={selectedReq.id}
                requirement={selectedReq}
                onChanged={reqs.setSelectedReq}
                onCaseCreated={onCaseCreated}
                onStartAnalysis={workspaceMode ? () => onStartAnalysis?.(selectedReq) ?? Promise.resolve() : undefined}
                analysisRunning={analysisRunning}
                showAnalyzeAction={!workspaceMode}
                showJourney={false}
              />
            </div>
          ) : (
            <div className="workspace-empty"><p>{t('pageSelectRequirement')}</p></div>
          )
      ) : (
        <div className="lc-requirements-layout">
          <RequirementList
            requirements={reqs.requirements}
            loading={reqs.loading}
            selectedReq={selectedReq}
            onSelect={handleSelectRequirement}
          />

          {selectedReq ? (
            <div
              style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}
            >
              <RequirementLifecyclePanel
                key={selectedReq.id}
                requirement={selectedReq}
                onChanged={reqs.setSelectedReq}
                onCaseCreated={onCaseCreated}
              />
              {!selectedReq.qa_model && (
                <>
                  <button
                    className="btn btn-secondary"
                    onClick={() => void ai.handleAnalyzeRequirementAI()}
                  >
                    {t('analysisTitle')}
                  </button>
                  <TestDesignPanel
                    testDesigns={designs.testDesigns}
                    onGenerateDesigns={ai.handleGenerateDesignsAI}
                    onAddManualDesign={() => designForm.open(selectedReq.id)}
                    onGenerateCases={ai.handleGenerateCasesAI}
                  />
                </>
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
                {t('pageSelectRequirement')}
              </div>
            </div>
          )}
        </div>
        )}

      <RequirementAnalysisModal
        progressEvents={ai.analysisProgress.events}
        progressError={ai.analysisProgress.error}
        isOpen={ai.isAiAnalysisOpen}
        analyzing={ai.analyzingReq}
        analysis={ai.aiAnalysis}
        onClose={() => {
          ai.analysisProgress.cancel();
          ai.setIsAiAnalysisOpen(false);
        }}
      />

      <TestDesignGenerationModal
        progressEvents={ai.designProgress.events}
        progressError={ai.designProgress.error}
        isOpen={ai.isAiDesignModalOpen}
        generating={ai.generatingDesigns}
        suggestions={ai.suggestedDesigns}
        onAdopt={ai.handleAdoptDesign}
        onClose={() => {
          ai.designProgress.cancel();
          ai.setIsAiDesignModalOpen(false);
        }}
      />

      <TestCaseGenerationModal
        progressEvents={ai.caseProgress.events}
        progressError={ai.caseProgress.error}
        isOpen={ai.isAiCaseModalOpen}
        generating={ai.generatingCases}
        activeDesign={ai.activeDesignForCases}
        cases={ai.suggestedCases}
        onAdopt={ai.handleAdoptCase}
        onClose={() => {
          ai.caseProgress.cancel();
          ai.setIsAiCaseModalOpen(false);
        }}
      />

      <RequirementFormModal
        isOpen={reqForm.isOpen}
        projects={projects}
        formData={reqForm.formData}
        setFormData={reqForm.setFormData}
        onSubmit={handleCreateRequirement}
        onClose={reqForm.close}
      />

      <TestDesignFormModal
        isOpen={designForm.isOpen}
        formData={designForm.formData}
        setFormData={designForm.setFormData}
        onSubmit={handleCreateTestDesign}
        onClose={designForm.close}
      />

      <JiraImportModal
        isOpen={jira.isJiraModalOpen}
        issues={jira.jiraIssues}
        searchQuery={jira.jiraSearchQuery}
        loading={jira.loadingJira}
        importing={jira.importingJira}
        selectedKeys={jira.selectedJiraKeys}
        onSearch={jira.handleSearchJira}
        onToggleKey={jira.toggleJiraKey}
        onImport={jira.handleImportJira}
        onClose={() => jira.setIsJiraModalOpen(false)}
      />
    </div>
  );
};
