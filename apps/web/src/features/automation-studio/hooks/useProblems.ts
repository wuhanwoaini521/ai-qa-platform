import { RefObject, useState } from 'react';
import { ValidationIssue } from '../../../types';
import { api } from '../../../api/client';
import { MonacoEditorInstance } from '../components/MonacoEditorPane';

interface UseProblemsOptions {
  projectId: string | null;
  openFile: (path: string) => void;
  /** Imperative handle used to reveal the offending line. */
  editorRef: RefObject<MonacoEditorInstance | null>;
}

export const useProblems = ({ projectId, openFile, editorRef }: UseProblemsOptions) => {
  // Bottom Problems Panel & Validation
  const [showProblemsPanel, setShowProblemsPanel] = useState<boolean>(false);
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[]>([]);
  const [validating, setValidating] = useState<boolean>(false);

  /** Toolbar action: validates with a spinner and opens the panel when issues are found. */
  const validateWorkspace = async () => {
    if (!projectId) return;
    try {
      setValidating(true);
      const res = await api.validateWorkspace(projectId);
      setValidationIssues(res.issues);
      if (res.issues.length > 0) {
        setShowProblemsPanel(true);
      }
    } catch (err) {
      console.error('Failed to validate workspace', err);
    } finally {
      setValidating(false);
    }
  };

  /** Post-save refresh: awaited by the caller, rejects so the save transaction can report it. */
  const refreshIssues = async () => {
    if (!projectId) return;
    const res = await api.validateWorkspace(projectId);
    setValidationIssues(res.issues);
  };

  /** Post-save refresh: no spinner, no error handling — matches the original fire-and-forget call. */
  const refreshIssuesInBackground = () => {
    if (!projectId) return;
    api.validateWorkspace(projectId).then((res) => setValidationIssues(res.issues));
  };

  // Jump editor to issue line
  const jumpToIssue = (issue: ValidationIssue) => {
    openFile(issue.file);
    setTimeout(() => {
      if (editorRef.current) {
        editorRef.current.revealLineInCenter(issue.line);
        editorRef.current.setPosition({ lineNumber: issue.line, column: issue.column || 1 });
        editorRef.current.focus();
      }
    }, 200);
  };

  return {
    validationIssues,
    validating,
    showProblemsPanel,
    setShowProblemsPanel,
    validateWorkspace,
    refreshIssues,
    refreshIssuesInBackground,
    jumpToIssue,
  };
};
