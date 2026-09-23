import React from 'react';
import { Project, Requirement } from '../../types';
import { useRequirements } from './hooks/useRequirements';
import { useTestDesigns } from './hooks/useTestDesigns';
import { useRequirementAI } from './hooks/useRequirementAI';
import { useJiraImport } from './hooks/useJiraImport';
import { RequirementToolbar } from './components/RequirementToolbar';
import { RequirementList } from './components/RequirementList';
import { RequirementDetail } from './components/RequirementDetail';
import { TestDesignPanel } from './components/TestDesignPanel';
import { RequirementAnalysisModal } from './components/RequirementAnalysisModal';
import { TestDesignGenerationModal } from './components/TestDesignGenerationModal';
import { TestCaseGenerationModal } from './components/TestCaseGenerationModal';
import { RequirementFormModal, useRequirementFormModal } from './components/RequirementFormModal';
import { TestDesignFormModal, useTestDesignFormModal } from './components/TestDesignFormModal';
import { JiraImportModal } from './components/JiraImportModal';

interface RequirementsPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onNavigateToStudio?: (filePath: string) => void;
  initialRequirementId?: string | null;
  onSelectRequirement?: (requirementId: string) => void;
}

export const RequirementsPage: React.FC<RequirementsPageProps> = ({
  projects,
  selectedProjectId,
  initialRequirementId,
  onSelectRequirement,
}) => {
  const reqForm = useRequirementFormModal(selectedProjectId || (projects[0]?.id ?? ''));
  const designForm = useTestDesignFormModal();

  const reqs = useRequirements({ selectedProjectId, projects, initialRequirementId });
  const designs = useTestDesigns(reqs.selectedReq);
  const ai = useRequirementAI({
    selectedReq: reqs.selectedReq,
    onDesignCreated: designs.appendDesign,
  });
  const jira = useJiraImport({ selectedProjectId, projects, onImported: reqs.addImported });

  const { selectedReq } = reqs;

  const handleSelectRequirement = (requirement: Requirement) => {
    reqs.setSelectedReq(requirement);
    onSelectRequirement?.(requirement.id);
  };

  const handleCreateRequirement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reqForm.formData.title.trim()) return;
    const created = await reqs.createRequirement(reqForm.formData);
    if (!created) return;
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
    <div>
      <RequirementToolbar
        projects={projects}
        onOpenJira={jira.handleOpenJiraModal}
        onNewRequirement={() => reqForm.open(selectedProjectId || projects[0]?.id || '')}
      />

      {projects.length === 0 ? (
        <div className="card">
          <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Please create a project first before creating requirements.
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: '20px' }}>
          <RequirementList
            requirements={reqs.requirements}
            loading={reqs.loading}
            selectedReq={selectedReq}
            onSelect={handleSelectRequirement}
          />

          {selectedReq ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <RequirementDetail
                selectedReq={selectedReq}
                onAnalyze={ai.handleAnalyzeRequirementAI}
                onUpdateStatus={reqs.updateStatus}
              />
              <TestDesignPanel
                testDesigns={designs.testDesigns}
                onGenerateDesigns={ai.handleGenerateDesignsAI}
                onAddManualDesign={() => designForm.open(selectedReq.id)}
                onGenerateCases={ai.handleGenerateCasesAI}
              />
            </div>
          ) : (
            <div className="card">
              <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Select a requirement to view details.
              </div>
            </div>
          )}
        </div>
      )}

      <RequirementAnalysisModal
        isOpen={ai.isAiAnalysisOpen}
        analyzing={ai.analyzingReq}
        analysis={ai.aiAnalysis}
        onClose={() => ai.setIsAiAnalysisOpen(false)}
      />

      <TestDesignGenerationModal
        isOpen={ai.isAiDesignModalOpen}
        generating={ai.generatingDesigns}
        suggestions={ai.suggestedDesigns}
        onAdopt={ai.handleAdoptDesign}
        onClose={() => ai.setIsAiDesignModalOpen(false)}
      />

      <TestCaseGenerationModal
        isOpen={ai.isAiCaseModalOpen}
        generating={ai.generatingCases}
        activeDesign={ai.activeDesignForCases}
        cases={ai.suggestedCases}
        onAdopt={ai.handleAdoptCase}
        onClose={() => ai.setIsAiCaseModalOpen(false)}
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
