import { RefObject, useEffect, useRef, useState } from 'react';
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
  const [stateProjectId, setStateProjectId] = useState(projectId);
  const [showProblemsPanel, setShowProblemsPanel] = useState<boolean>(false);
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[]>([]);
  const [validating, setValidating] = useState<boolean>(false);
  const [hasValidated, setHasValidated] = useState<boolean>(false);
  const [validationFailed, setValidationFailed] = useState<boolean>(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    requestIdRef.current += 1;
    setStateProjectId(projectId);
    setValidationIssues([]);
    setValidating(false);
    setHasValidated(false);
    setValidationFailed(false);
    return () => { requestIdRef.current += 1; };
  }, [projectId]);

  /** Explicit toolbar action: validate the selected project and show the result. */
  const validateWorkspace = async () => {
    if (!projectId) return;
    const requestId = ++requestIdRef.current;
    setHasValidated(false);
    setValidationIssues([]);
    setValidationFailed(false);
    setShowProblemsPanel(true);
    try {
      setValidating(true);
      const res = await api.validateWorkspace(projectId);
      if (requestId !== requestIdRef.current) return;
      setValidationIssues(res.issues);
      setHasValidated(true);
      setShowProblemsPanel(true);
    } catch {
      if (requestId === requestIdRef.current) {
        setValidationFailed(true);
        setShowProblemsPanel(true);
      }
    } finally {
      if (requestId === requestIdRef.current) setValidating(false);
    }
  };

  /** Post-save refresh: awaited by the caller, rejects so the save transaction can report it. */
  const refreshIssues = async () => {
    if (!projectId) return;
    const requestId = ++requestIdRef.current;
    setHasValidated(false);
    setValidationIssues([]);
    setValidationFailed(false);
    setValidating(true);
    try {
      const res = await api.validateWorkspace(projectId);
      if (requestId !== requestIdRef.current) return;
      setValidationIssues(res.issues);
      setHasValidated(true);
    } catch (error) {
      if (requestId === requestIdRef.current) setValidationFailed(true);
      throw error;
    } finally {
      if (requestId === requestIdRef.current) setValidating(false);
    }
  };

  /** Refresh after an explicit save without blocking the editor. */
  const refreshIssuesInBackground = () => {
    if (!projectId) return;
    const requestId = ++requestIdRef.current;
    setHasValidated(false);
    setValidationIssues([]);
    setValidationFailed(false);
    setValidating(true);
    api.validateWorkspace(projectId).then((res) => {
      if (requestId !== requestIdRef.current) return;
      setValidationIssues(res.issues);
      setHasValidated(true);
    }).catch(() => {
      if (requestId === requestIdRef.current) setValidationFailed(true);
    }).finally(() => {
      if (requestId === requestIdRef.current) setValidating(false);
    });
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

  const isCurrentProject = stateProjectId === projectId;

  return {
    validationIssues: isCurrentProject ? validationIssues : [],
    validating: isCurrentProject && validating,
    hasValidated: isCurrentProject && hasValidated,
    validationFailed: isCurrentProject && validationFailed,
    showProblemsPanel,
    setShowProblemsPanel,
    validateWorkspace,
    refreshIssues,
    refreshIssuesInBackground,
    jumpToIssue,
  };
};
