import { useState } from 'react';
import { api } from '../../../api/client';
import { JiraIssue, Project, Requirement } from '../../../types';

interface UseJiraImportOptions {
  selectedProjectId: string | null;
  projects: Project[];
  onImported: (imported: Requirement[]) => void;
}

export function useJiraImport({ selectedProjectId, projects, onImported }: UseJiraImportOptions) {
  const [isJiraModalOpen, setIsJiraModalOpen] = useState(false);
  const [jiraIssues, setJiraIssues] = useState<JiraIssue[]>([]);
  const [jiraSearchQuery, setJiraSearchQuery] = useState('');
  const [selectedJiraKeys, setSelectedJiraKeys] = useState<string[]>([]);
  const [loadingJira, setLoadingJira] = useState(false);
  const [importingJira, setImportingJira] = useState(false);

  const handleOpenJiraModal = async () => {
    setIsJiraModalOpen(true);
    setLoadingJira(true);
    try {
      const issues = await api.searchJiraIssues();
      setJiraIssues(issues);
      setSelectedJiraKeys([]);
    } catch (err) {
      console.error('Failed to search Jira issues', err);
    } finally {
      setLoadingJira(false);
    }
  };

  const handleSearchJira = async (q: string) => {
    setJiraSearchQuery(q);
    setLoadingJira(true);
    try {
      const issues = await api.searchJiraIssues(q);
      setJiraIssues(issues);
    } catch (err) {
      console.error('Failed to search Jira issues', err);
    } finally {
      setLoadingJira(false);
    }
  };

  const toggleJiraKey = (key: string) => {
    if (selectedJiraKeys.includes(key)) {
      setSelectedJiraKeys(selectedJiraKeys.filter((k) => k !== key));
    } else {
      setSelectedJiraKeys([...selectedJiraKeys, key]);
    }
  };

  const handleImportJira = async () => {
    if (selectedJiraKeys.length === 0) return;
    const projId = selectedProjectId || projects[0]?.id;
    if (!projId) return;
    setImportingJira(true);
    try {
      const imported = await api.importJiraIssues({
        issue_keys: selectedJiraKeys,
        project_id: projId,
      });
      onImported(imported);
      setIsJiraModalOpen(false);
    } catch (err) {
      console.error('Failed to import Jira issues', err);
    } finally {
      setImportingJira(false);
    }
  };

  return {
    isJiraModalOpen,
    setIsJiraModalOpen,
    jiraIssues,
    jiraSearchQuery,
    selectedJiraKeys,
    loadingJira,
    importingJira,
    handleOpenJiraModal,
    handleSearchJira,
    toggleJiraKey,
    handleImportJira,
  };
}
