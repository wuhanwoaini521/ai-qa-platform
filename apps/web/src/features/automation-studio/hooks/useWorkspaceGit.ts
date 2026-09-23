import { useState } from 'react';
import {
  BranchInfo,
  CheckRun,
  GitCommitInfo,
  GitDiffResult,
  PRChecksSummary,
  PRDiagnosisResponse,
  PullRequestInfo,
} from '../../../types';
import { api } from '../../../api/client';
import { errorText } from '../errorText';

interface UseWorkspaceGitOptions {
  /** Working tree changed (branch create/switch) — refreshes the file explorer. */
  onWorkspaceFilesChanged?: () => Promise<void> | void;
  /** A PR was created — the sidebar switches to the PR view. */
  onSelectPRTab?: () => void;
}

export const useWorkspaceGit = (projectId: string | null, options: UseWorkspaceGitOptions = {}) => {
  const { onWorkspaceFilesChanged, onSelectPRTab } = options;

  // Source Control & Branch Workflow (Phase 8)
  const [currentBranch, setCurrentBranch] = useState<string>('main');
  const [branches, setBranches] = useState<BranchInfo[]>([]);
  const [recentCommits, setRecentCommits] = useState<GitCommitInfo[]>([]);
  const [showBranchModal, setShowBranchModal] = useState<boolean>(false);
  const [newBranchInput, setNewBranchInput] = useState<string>('');
  const [isPushing, setIsPushing] = useState<boolean>(false);
  const [pushStatusMessage, setPushStatusMessage] = useState<string | null>(null);
  const [suggestingCommit, setSuggestingCommit] = useState<boolean>(false);

  // Pull Request & GitHub Checks Workflow (Phase 8)
  const [activePR, setActivePR] = useState<PullRequestInfo | null>(null);
  const [prChecks, setPRChecks] = useState<PRChecksSummary | null>(null);
  const [showPRModal, setShowPRModal] = useState<boolean>(false);
  const [prTitleInput, setPRTitleInput] = useState<string>('');
  const [prBodyInput, setPRBodyInput] = useState<string>('');
  const [suggestingPR, setSuggestingPR] = useState<boolean>(false);
  const [creatingPR, setCreatingPR] = useState<boolean>(false);
  const [loadingChecks, setLoadingChecks] = useState<boolean>(false);
  const [diagnosingCheckId, setDiagnosingCheckId] = useState<string | null>(null);
  const [ciDiagnosisResult, setCIDiagnosisResult] = useState<PRDiagnosisResponse | null>(null);

  // Source Control & Commit
  const [diffResult, setDiffResult] = useState<GitDiffResult>({ diff: '', changed_files: [] });
  const [showDiffView, setShowDiffView] = useState<boolean>(false);
  const [commitMessage, setCommitMessage] = useState<string>('');
  const [isCommitting, setIsCommitting] = useState<boolean>(false);

  const fetchGitData = async () => {
    if (!projectId) return;
    try {
      const [curBranch, branchList, commits, _status, diff] = await Promise.all([
        api.getCurrentBranch(projectId).catch(() => 'main'),
        api.getGitBranches(projectId).catch(() => []),
        api.getGitLog(projectId, 15).catch(() => []),
        api.getGitStatus(projectId).catch(() => []),
        api.getWorkspaceDiff(projectId).catch(() => ({ diff: '', changed_files: [] })),
      ]);
      setCurrentBranch(curBranch);
      setBranches(branchList);
      setRecentCommits(commits);
      setDiffResult(diff);
    } catch (err) {
      console.error('Failed to fetch Git data', err);
    }
  };

  /** Re-reads the working-tree diff into `diffResult`; rejects so callers can report the failure. */
  const refreshDiff = async () => {
    if (!projectId) return;
    const diff = await api.getWorkspaceDiff(projectId);
    setDiffResult(diff);
  };

  const hideDiffView = () => setShowDiffView(false);

  const handleCreateBranch = async () => {
    if (!projectId || !newBranchInput.trim()) return;
    try {
      await api.createBranch(projectId, { branch_name: newBranchInput.trim(), checkout: true });
      setNewBranchInput('');
      setShowBranchModal(false);
      await fetchGitData();
      await onWorkspaceFilesChanged?.();
    } catch (err) {
      alert(`Create branch error: ${errorText(err)}`);
    }
  };

  const handleSwitchBranch = async (targetBranch: string) => {
    if (!projectId || targetBranch === currentBranch) return;
    try {
      await api.switchBranch(projectId, { branch_name: targetBranch });
      await fetchGitData();
      await onWorkspaceFilesChanged?.();
    } catch (err) {
      alert(`Switch branch error: ${errorText(err)}`);
    }
  };

  const handleSuggestCommitMessage = async () => {
    if (!projectId || suggestingCommit) return;
    try {
      setSuggestingCommit(true);
      const diff = await api.getWorkspaceDiff(projectId);
      if (diff.changed_files.length > 0) {
        setCommitMessage(`feat(${currentBranch}): update automated test suites (${diff.changed_files.length} files)`);
      } else {
        setCommitMessage(`chore(${currentBranch}): workspace maintenance`);
      }
    } catch (err) {
      console.error('Failed to suggest commit msg', err);
    } finally {
      setSuggestingCommit(false);
    }
  };

  const handleCommitChanges = async () => {
    if (!projectId || !commitMessage.trim() || isCommitting) return;
    try {
      setIsCommitting(true);
      await api.commitWorkspace(projectId, commitMessage.trim());
      setCommitMessage('');
      await fetchGitData();
      setShowDiffView(false);
    } catch (err) {
      alert(`Commit error: ${errorText(err)}`);
    } finally {
      setIsCommitting(false);
    }
  };

  const handlePushBranch = async () => {
    if (!projectId || isPushing) return;
    try {
      setIsPushing(true);
      setPushStatusMessage('Pushing branch to origin...');
      const res = await api.pushGitBranch(projectId, currentBranch);
      setPushStatusMessage(res.message);
      await fetchGitData();
    } catch (err) {
      setPushStatusMessage(`Push error: ${errorText(err)}`);
    } finally {
      setIsPushing(false);
    }
  };

  const handleOpenPRModal = async () => {
    if (!projectId) return;
    try {
      setShowPRModal(true);
      setSuggestingPR(true);
      const suggestion = await api.suggestPRSummary(projectId, { include_diff: true });
      setPRTitleInput(suggestion.title);
      setPRBodyInput(suggestion.body);
    } catch (err) {
      setPRTitleInput(`feat(${currentBranch}): automated test suite coverage`);
      setPRBodyInput(`## Quality Engineering PR\n\nAutomated tests for branch \`${currentBranch}\`.`);
    } finally {
      setSuggestingPR(false);
    }
  };

  const handleCreatePR = async () => {
    if (!projectId || !prTitleInput.trim() || creatingPR) return;
    try {
      setCreatingPR(true);
      const pr = await api.createPullRequest(projectId, {
        title: prTitleInput.trim(),
        body: prBodyInput,
        head_branch: currentBranch,
        base_branch: 'main',
      });
      setActivePR(pr);
      setShowPRModal(false);
      onSelectPRTab?.();
      if (pr.checks_summary) {
        setPRChecks(pr.checks_summary);
      }
    } catch (err) {
      alert(`PR creation error: ${errorText(err)}`);
    } finally {
      setCreatingPR(false);
    }
  };

  const handleRefreshPRChecks = async () => {
    if (!projectId || !activePR) return;
    try {
      setLoadingChecks(true);
      const checks = await api.getPRChecks(projectId, activePR.number);
      setPRChecks(checks);
    } catch (err) {
      console.error('Failed to refresh PR checks', err);
    } finally {
      setLoadingChecks(false);
    }
  };

  const handleDiagnoseCI = async (check: CheckRun) => {
    if (!projectId) return;
    try {
      setDiagnosingCheckId(check.id);
      const diag = await api.diagnosePRFailure(projectId, {
        check_run_id: check.id,
        failure_logs: check.failure_logs || check.failure_summary || 'CI check failure',
      });
      setCIDiagnosisResult(diag);
    } catch (err) {
      alert(`Diagnosis failed: ${errorText(err)}`);
    } finally {
      setDiagnosingCheckId(null);
    }
  };

  return {
    currentBranch,
    branches,
    recentCommits,
    showBranchModal,
    setShowBranchModal,
    newBranchInput,
    setNewBranchInput,
    isPushing,
    pushStatusMessage,
    suggestingCommit,
    activePR,
    prChecks,
    showPRModal,
    setShowPRModal,
    prTitleInput,
    setPRTitleInput,
    prBodyInput,
    setPRBodyInput,
    suggestingPR,
    creatingPR,
    loadingChecks,
    diagnosingCheckId,
    ciDiagnosisResult,
    setCIDiagnosisResult,
    diffResult,
    setDiffResult,
    showDiffView,
    setShowDiffView,
    hideDiffView,
    commitMessage,
    setCommitMessage,
    isCommitting,
    fetchGitData,
    refreshDiff,
    handleCreateBranch,
    handleSwitchBranch,
    handleSuggestCommitMessage,
    handleCommitChanges,
    handlePushBranch,
    handleOpenPRModal,
    handleCreatePR,
    handleRefreshPRChecks,
    handleDiagnoseCI,
  };
};
