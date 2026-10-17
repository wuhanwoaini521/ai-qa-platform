import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bug, CheckCircle2, ChevronDown, FileCode2, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Play, Save } from 'lucide-react';
import { api } from '../../api/client';
import { Breakpoint, Project, TestCase } from '../../types';
import { Link, useSearchParams } from 'react-router-dom';
import { KnowledgeDrawer } from '../lifecycle/KnowledgeDrawer';
import { StudioRunPanel } from '../lifecycle/StudioRunPanel';
import { CommandPalette } from '../lifecycle/CommandPalette';
import '../lifecycle/lifecycle.css';
import { FileOpModalState, SidebarTab } from './types';
import { errorText } from './errorText';
import { resolveStudioRunTarget } from './runTarget';
import { useWorkspaceFiles } from './hooks/useWorkspaceFiles';
import { useEditorTabs } from './hooks/useEditorTabs';
import { useWorkspaceGit } from './hooks/useWorkspaceGit';
import { useTestExplorer } from './hooks/useTestExplorer';
import { useProblems } from './hooks/useProblems';
import { useQAAssistant } from './hooks/useQAAssistant';
import { useRunExecution, type StudioRunConfig } from './hooks/useRunExecution';
import { useDebugSession, type DebugStackFrame } from './hooks/useDebugSession';
import { RuntimeMiniBar } from '../runtime/RuntimeMiniBar';
import { useRuntimeSnapshot } from '../runtime/useRuntimeSnapshot';
import { MonacoEditorInstance, MonacoEditorPane } from './components/MonacoEditorPane';
import { ProjectSelector } from './components/ProjectSelector';
import { SidebarViewSwitcher } from './components/SidebarViewSwitcher';
import { SidebarActionHeader } from './components/SidebarActionHeader';
import { FileTree } from './components/FileTree';
import { TestExplorer } from './components/TestExplorer';
import { SourceControlPanel } from './components/SourceControlPanel';
import { PullRequestPanel } from './components/PullRequestPanel';
import { EditorTabs } from './components/EditorTabs';
import { WorkbenchStatusBar } from './components/WorkbenchStatusBar';
import { ProblemsPanel } from './components/ProblemsPanel';
import { RunOutputPanel } from './components/RunOutputPanel';
import { QAAssistantPanel } from './components/QAAssistantPanel';
import { useContextTask } from '../../components/ContextTaskProgress';
import { QuickOpen } from './components/QuickOpen';
import { FileOpModal } from './components/FileOpModal';
import { BranchModal } from './components/BranchModal';
import { PullRequestModal } from './components/PullRequestModal';
import { DebugPanel } from './components/DebugPanel';
import { buildWorkspaceHref, readWorkspaceContext } from '../../app/workspaceContext';
import { usePaneResize } from '../workspace/usePaneResize';

export interface AutomationStudioPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onSelectProject: (id: string) => void;
  onNavigateToRuns?: (runId?: string) => void;
  onRunCreated?: (runId: string) => void;
  runConfig?: StudioRunConfig;
  embedded?: boolean;
  workspaceView?: 'code' | 'debug';
  initialOpenFilePath?: string | null;
  initialOpenLineNumber?: number | null;
  initialDebugNodeId?: string | null;
  initialDebugFailureId?: string | null;
  workspaceAutomationSetup?: 'no-case' | 'unbound' | null;
  workspaceAutomationSetupKey?: string;
  onStartRecording?: () => void;
  onSelectCases?: () => void;
}

export const AutomationStudioPage: React.FC<AutomationStudioPageProps> = ({
  projects,
  selectedProjectId,
  onSelectProject,
  onNavigateToRuns,
  onRunCreated,
  runConfig,
  embedded = false,
  workspaceView,
  initialOpenFilePath,
  initialOpenLineNumber,
  initialDebugNodeId,
  initialDebugFailureId,
  workspaceAutomationSetup,
  workspaceAutomationSetupKey,
  onStartRecording,
  onSelectCases,
}) => {
  const { t } = useTranslation('studioShell');
  const { t: lc } = useTranslation('lifecycle');
  const [query,setQuery] = useSearchParams();
  const [showBrowser,setShowBrowser]=useState(false);
  const [showAssistant,setShowAssistant]=useState(false);
  const [showContext,setShowContext]=useState(!initialDebugNodeId && !embedded);
  const [showFiles,setShowFiles]=useState(() => !embedded || !window.matchMedia('(max-width: 820px)').matches);
  const [showCommands,setShowCommands]=useState(false);
  const [showKnowledge,setShowKnowledge]=useState(false);
  const browserDrawerRef=useRef<HTMLElement>(null);
  const toolsMenuRef=useRef<HTMLDetailsElement>(null);
  const toolsMenuTriggerRef=useRef<HTMLElement>(null);
  const [projectCases,setProjectCases]=useState<TestCase[]>([]);
  const queryPreset = query.get('preset');
  const preset = embedded && workspaceView
    ? queryPreset === 'review' && workspaceView === 'code' ? 'review' : workspaceView
    : queryPreset ?? 'code';
  const closeToolsMenu = () => {
    if (toolsMenuRef.current) toolsMenuRef.current.open = false;
  };
  const currentProjectId = selectedProjectId || projects[0]?.id || null;
  useEffect(()=>{let disposed=false;setProjectCases([]);if(currentProjectId)api.getTestCases(currentProjectId).then(items=>{if(!disposed)setProjectCases(items);}).catch(()=>{});return()=>{disposed=true;};},[currentProjectId]);
  useEffect(() => {
    setShowBrowser(preset === 'record');
    setShowAssistant(preset === 'review');
    setShowContext(!initialDebugNodeId && !embedded);
    const narrowViewport = window.matchMedia('(max-width: 820px)');
    const updateFileVisibility = () => setShowFiles(preset !== 'debug' && (!embedded || !narrowViewport.matches));
    updateFileVisibility();
    narrowViewport.addEventListener('change', updateFileVisibility);
    return () => narrowViewport.removeEventListener('change', updateFileVisibility);
  }, [preset, currentProjectId, initialDebugNodeId, embedded]);
  const generateTask = useContextTask(currentProjectId, 'studio', currentProjectId);

  // Cross-panel UI state (read/written by more than one panel)
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>('files');
  const [fileOpModal, setFileOpModal] = useState<FileOpModalState | null>(null);
  const [opInputText, setOpInputText] = useState<string>('');
  const [setupCaseId, setSetupCaseId] = useState<string | null>(null);
  const [showQuickOpen, setShowQuickOpen] = useState<boolean>(false);
  const [quickOpenQuery, setQuickOpenQuery] = useState<string>('');
  const [quickOpenSelectedIndex, setQuickOpenSelectedIndex] = useState<number>(0);
  const [breakpoints, setBreakpoints] = useState<Breakpoint[]>([]);
  const [debugPreparationError, setDebugPreparationError] = useState('');
  const [sourceFocus, setSourceFocus] = useState<{ path: string; line: number } | null>(null);
  const [languageIssues, setLanguageIssues] = useState<Record<string, import('../../types').ValidationIssue[]>>({});
  useEffect(() => { setLanguageIssues({}); }, [currentProjectId]);
  const [executionLocation, setExecutionLocation] = useState<{ path: string; line: number } | null>(null);
  const bottomDock = usePaneResize({ storageKey: 'studio.bottomPanelHeight', min: 120, max: 520, initial: 220 });

  const closeBrowserDrawer=()=>{setShowBrowser(false);toolsMenuTriggerRef.current?.focus();};
  const handleBrowserDrawerKeyDown=(event:React.KeyboardEvent<HTMLDivElement>)=>{
    if(event.key==='Escape'){
      event.preventDefault();
      event.stopPropagation();
      closeBrowserDrawer();
      return;
    }
    if(event.key!=='Tab')return;
    const drawer=browserDrawerRef.current;
    if(!drawer)return;
    const focusable=Array.from(drawer.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')).filter(element=>element.getClientRects().length>0);
    if(focusable.length===0){event.preventDefault();drawer.focus();return;}
    const first=focusable[0];
    const last=focusable[focusable.length-1];
    const active=document.activeElement;
    if(!drawer.contains(active)){
      event.preventDefault();
      (event.shiftKey?last:first).focus();
    }else if(event.shiftKey&&active===first){
      event.preventDefault();
      last.focus();
    }else if(!event.shiftKey&&active===last){
      event.preventDefault();
      first.focus();
    }
  };

  // Monaco Editor Ref
  const editorRef = useRef<MonacoEditorInstance | null>(null);

  // Glue for two cross-hook cycles: Git branch ops refresh the file tree; the problems panel
  // re-opens a file through the tab store.
  const fetchFilesRef = useRef<() => Promise<void>>(async () => {});
  const openFileRef = useRef<(path: string) => void>(() => {});

  const git = useWorkspaceGit(currentProjectId, {
    onWorkspaceFilesChanged: () => fetchFilesRef.current(),
    onSelectPRTab: () => setSidebarTab('pr'),
  });
  const workspace = useWorkspaceFiles(currentProjectId, { onDiffLoaded: git.setDiffResult });
  const tests = useTestExplorer(currentProjectId);
  const problems = useProblems({ projectId: currentProjectId, openFile: (p) => openFileRef.current(p), editorRef });
  const editor = useEditorTabs({
    projectId: currentProjectId,
    setLoadingFile: workspace.setLoadingFile,
    hideDiffView: git.hideDiffView,
    // Runs inside the save transaction: the diff is awaited, validation and the test
    // collection are refreshed in the background — same ordering as before the split.
    onAfterSave: async (path) => {
      await git.refreshDiff();
      problems.refreshIssuesInBackground();
      if (path.includes('test_') || path.endsWith('.py')) {
        tests.refreshTestsInBackground();
      }
    },
    onAfterSaveAll: async () => {
      await git.refreshDiff();
      await problems.refreshIssues();
    },
  });
  const openStudioFile = (path: string) => {
    if (workspaceAutomationSetup && workspaceAutomationSetupKey) setSetupCaseId(workspaceAutomationSetupKey);
    return editor.openFile(path);
  };
  const openSidebarFile = (path: string) => {
    void openStudioFile(path);
    if (embedded && window.matchMedia('(max-width: 820px)').matches) setShowFiles(false);
  };
  const openStudioFileRef = useRef(openStudioFile);
  openStudioFileRef.current = openStudioFile;
  const showAutomationSetup = Boolean(workspaceAutomationSetup && setupCaseId !== workspaceAutomationSetupKey);
  const assistant = useQAAssistant({
    projectId: currentProjectId,
    activeTab: editor.activeTab,
    editorRef,
    onInsertFallback: editor.updateContent,
    caseId: query.get('caseId'),
  });
  const failureId = query.get('failureId');
  const parentRunId = query.get('parentRunId');
  const studioContext = readWorkspaceContext(query, currentProjectId);
  const run = useRunExecution({ projectId: currentProjectId, runConfig, activeTabPath: editor.activeTabPath, onNavigateToRuns, onRunCreated, retryContext: failureId && parentRunId ? { failureId, runId: parentRunId } : undefined });
  useEffect(() => {
    if (!embedded && run.activeRunId) setShowBrowser(true);
  }, [embedded, run.activeRunId]);
  const hasRunRuntime = Boolean(run.activeRunId || (!studioContext.taskId && studioContext.runId));
  const runtimeId = run.activeRunId ?? studioContext.taskId ?? studioContext.runId ?? '';
  const runtimeKind = hasRunRuntime ? 'run' : 'task';
  const studioRuntime = useRuntimeSnapshot(runtimeKind, runtimeId);
  useEffect(()=>{if(showBrowser)browserDrawerRef.current?.focus();},[showBrowser]);
  const linkedCase=projectCases.find(item=>item.id===query.get('caseId'));
  const caseNodeid = linkedCase?.binding?.nodeid ?? (
    query.get('caseId') && !linkedCase ? query.get('nodeid') ?? undefined : undefined
  );
  const saveAndRun = async (target?: string) => {
    if (!editor.activeTabPath && !target && !caseNodeid) {
      setDebugPreparationError(lc('noSourceFile'));
      return;
    }
    if (await editor.saveAll()) {
      await run.runExecution(resolveStudioRunTarget(editor.activeTabPath, target, caseNodeid));
    }
  };
  const runCurrentRef=useRef(saveAndRun);runCurrentRef.current=saveAndRun;
  const debug = useDebugSession({
    projectId: currentProjectId,
    breakpoints,
    onOpenFile: openStudioFile,
    onExecutionLine: setExecutionLocation,
    onBreakpoints: (sessionBreakpoints) => {
      setBreakpoints((items) => [
        ...items.filter((item) => !sessionBreakpoints.some((sessionBreakpoint) => sessionBreakpoint.id === item.id)),
        ...sessionBreakpoints,
      ]);
    },
  });
  const startDebug = async (nodeid: string, failureId?: string | null) => {
    setDebugPreparationError('');
    if (!await editor.saveAll()) {
      setDebugPreparationError(t('debug.saveFailed', { ns: 'studioPanels' }));
      return;
    }
    await debug.start(nodeid, failureId);
  };
  const debugStartRef = useRef(startDebug);
  const autoDebugStartedRef = useRef<string | null>(null);
  const autoSelectedFrameRef = useRef<DebugStackFrame | null>(null);
  debugStartRef.current = startDebug;
  const activeFilePath = editor.activeTab?.path.replace(/\\/g, '/').replace(/^\/+/, '');
  // The toolbar debugs the active test module, so breakpoints in any of its cases can be hit.
  // Explicit case debugging remains available in the test explorer and failure deep links.
  const debugTargetNodeId = activeFilePath && tests.collectedTests.some(
    (test) => test.path.replace(/\\/g, '/').replace(/^\/+/, '') === activeFilePath,
  ) ? activeFilePath : null;

  const problemCount = problems.validationIssues.length + Object.values(languageIssues).flat().length;

  fetchFilesRef.current = workspace.fetchFiles;
  openFileRef.current = openStudioFile;
  const refreshTestsRef = useRef(tests.refreshTestsInBackground);
  refreshTestsRef.current = tests.refreshTestsInBackground;

  useEffect(() => {
    workspace.fetchFiles();
    git.fetchGitData();
  }, [currentProjectId]);

  useEffect(() => {
    let active = true;
    setBreakpoints([]);
    if (currentProjectId) {
      void api.getBreakpoints(currentProjectId).then((items) => {
        if (active) setBreakpoints(items);
      }).catch((error) => console.error('Failed to load workspace breakpoints', error));
    }
    return () => { active = false; };
  }, [currentProjectId]);

  const toggleBreakpoint = async (filePath: string, lineNumber: number) => {
    if (!currentProjectId || !filePath) return;
    const normalizedPath = filePath.replace(/\\/g, '/').replace(/^\/+/, '');
    const current = breakpoints.find((item) => item.file_path === normalizedPath && item.line_number === lineNumber);
    try {
      if (current) {
        await api.deleteBreakpoint(currentProjectId, current.id);
        setBreakpoints((items) => items.filter((item) => item.id !== current.id));
      } else {
        const created = await api.upsertBreakpoint(currentProjectId, {
          file_path: normalizedPath,
          line_number: lineNumber,
          enabled: true,
          source: 'manual',
        });
        setBreakpoints((items) => [...items, created]);
      }
    } catch (error) {
      console.error('Failed to toggle breakpoint', error);
    }
  };

  useEffect(() => {
    if (!initialOpenFilePath) return;
    void openStudioFileRef.current(initialOpenFilePath).then(() => {
      void fetchFilesRef.current();
      refreshTestsRef.current();
    });
  }, [initialOpenFilePath]);

  useEffect(() => {
    if (!initialDebugNodeId || !currentProjectId) return;
    const target = currentProjectId + '::' + initialDebugNodeId + '::' + (initialDebugFailureId ?? '');
    if (autoDebugStartedRef.current === target) return;
    autoDebugStartedRef.current = target;
    void debugStartRef.current(initialDebugNodeId, initialDebugFailureId);
  }, [currentProjectId, initialDebugFailureId, initialDebugNodeId]);

  useEffect(() => {
    const frame = debug.frames[0];
    const framePath = frame?.source?.path?.replace(/\\/g, '/').replace(/^\/+/, '');
    const activePath = editor.activeTab?.path.replace(/\\/g, '/').replace(/^\/+/, '');
    if (
      debug.state !== 'paused' ||
      !frame ||
      !framePath ||
      framePath !== activePath ||
      autoSelectedFrameRef.current === frame
    ) return;
    autoSelectedFrameRef.current = frame;
    void debug.selectFrame(frame);
  }, [debug.frames, debug.selectFrame, debug.state, editor.activeTab?.path, workspace.loadingFile]);

  // Keyboard Shortcuts (Cmd/Ctrl + S, Cmd/Ctrl + Shift + S, Cmd/Ctrl + P)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();void runCurrentRef.current();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();setShowCommands(v=>!v);
      } else if ((e.metaKey || e.ctrlKey) && e.key === 'p') {
        e.preventDefault();
        setShowQuickOpen((prev) => !prev);
        setQuickOpenQuery('');
        setQuickOpenSelectedIndex(0);
      } else if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === 'S' || e.key === 's')) {
        e.preventDefault();
        editor.saveAll();
      } else if ((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        editor.saveActiveTab();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [editor.saveActiveTab, editor.saveAll]);

  const handleSelectSidebarTab = (tab: SidebarTab) => {
    setSidebarTab(tab);
    if (tab === 'git') git.fetchGitData();
    if (tab === 'pr' && git.activePR) git.handleRefreshPRChecks();
  };

  const handleRefreshAll = () => {
    workspace.fetchFiles();
    tests.fetchCollectedTests();
    git.fetchGitData();
    if (git.activePR) git.handleRefreshPRChecks();
  };

  // File Operations Execution
  const handleExecuteFileOp = async () => {
    if (!currentProjectId || !fileOpModal) return;
    const input = opInputText.trim();
    if (!input && fileOpModal.type !== 'delete') return;

    try {
      if (fileOpModal.type === 'create_file') {
        await workspace.createWorkspaceFile(input);
        await workspace.fetchFiles();
        openStudioFile(input);
      } else if (fileOpModal.type === 'create_folder') {
        await workspace.createWorkspaceDirectory(input);
        await workspace.fetchFiles();
      } else if (fileOpModal.type === 'rename' && fileOpModal.targetPath) {
        await workspace.renameWorkspaceEntry(fileOpModal.targetPath, input);
        await workspace.fetchFiles();
        // Update tabs
        editor.renameTab(fileOpModal.targetPath, input);
      } else if (fileOpModal.type === 'delete' && fileOpModal.targetPath) {
        await workspace.deleteWorkspaceEntry(fileOpModal.targetPath);
        await workspace.fetchFiles();
        editor.closeTab(fileOpModal.targetPath);
      }
    } catch (err) {
      alert(t('error.fileOperation', { message: errorText(err) }));
    } finally {
      setFileOpModal(null);
      setOpInputText('');
    }
  };

  const handleBootstrapWorkspace = async () => {
    if (!currentProjectId) return;
    try {
      await workspace.bootstrapWorkspace();
      await tests.fetchCollectedTests();
    } catch (err) {
      console.error('Failed to bootstrap workspace', err);
    }
  };

  if (!currentProjectId || projects.length === 0) {
    return (
      <div className="card" style={{ margin: '20px' }}>
        <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
          {t('selectProjectFirst')}
        </div>
      </div>
    );
  }

  const failureReturnHref = failureId
    ? studioContext.returnTo === 'workspace'
      ? buildWorkspaceHref({ ...studioContext, projectId: currentProjectId, stage: 'failure' })
      : `/failures/${encodeURIComponent(failureId)}`
    : null;
  const workspaceReturnHref = studioContext.returnTo === 'workspace'
    ? buildWorkspaceHref({ ...studioContext, projectId: currentProjectId })
    : null;
  const returnHref = failureReturnHref ?? workspaceReturnHref;
  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%',minHeight:0}}>
      <div className="lc-preset-bar lc-studio-toolbar">
        {!embedded && <div className="lc-studio-breadcrumb">
          <Link to={`/projects/${currentProjectId}`}>{projects.find(p=>p.id===currentProjectId)?.name}</Link>
          <span>/ Studio</span>
          {returnHref && <Link className="btn btn-secondary btn-sm" to={returnHref}>{failureReturnHref ? lc('returnToFailureContext') : lc('returnToWorkspace')}</Link>}
        </div>}
        {embedded && <button type="button" className="btn btn-secondary btn-sm lc-studio-files-toggle" aria-pressed={showFiles} aria-controls="studio-workspace-files" onClick={() => setShowFiles((visible) => !visible)} title={lc('workspaceFiles')}>
          {showFiles ? <PanelLeftClose size={14} aria-hidden="true" /> : <PanelLeftOpen size={14} aria-hidden="true" />}
          <span>{lc('workspaceFiles')}</span>
        </button>}
        <details className="lc-studio-tools" ref={toolsMenuRef} onBlur={(event) => {
          const nextTarget = event.relatedTarget;
          if (!(nextTarget instanceof Node) || !event.currentTarget.contains(nextTarget)) {
            event.currentTarget.open = false;
          }
        }}>
          <summary ref={toolsMenuTriggerRef} className="btn btn-secondary btn-sm" aria-label={lc('panelTools')}>
            <MoreHorizontal size={15} aria-hidden="true" />
            <span>{lc('panelTools')}</span>
            <ChevronDown size={13} aria-hidden="true" />
          </summary>
          <div className="lc-studio-tools-menu" role="group" aria-label={lc('panelTools')}>
            {!embedded && <button type="button" aria-pressed={showFiles} onClick={() => { setShowFiles(value => !value); closeToolsMenu(); }}>{lc('workspaceFiles')}</button>}
            <button type="button" aria-pressed={showContext} onClick={() => { setShowContext(value => !value); closeToolsMenu(); }}>{lc('context')}</button>
            <button type="button" aria-pressed={problems.showProblemsPanel} onClick={() => { problems.setShowProblemsPanel(value => !value); closeToolsMenu(); }}>{t('editor.problems', { problemCount })}</button>
            <button type="button" aria-pressed={showBrowser} onClick={() => { showBrowser ? setShowBrowser(false) : setShowBrowser(true); closeToolsMenu(); }}>{lc('showBrowser')}</button>
            <button type="button" aria-pressed={showAssistant} onClick={() => { setShowAssistant(value => !value); closeToolsMenu(); }}>{lc('assistant')}</button>
            <button type="button" onClick={() => { setShowCommands(true); closeToolsMenu(); }}>{lc('commands')} <span>⌃K</span></button>
          </div>
        </details>
      </div>
      {!embedded && runtimeId && studioRuntime.snapshot && <RuntimeMiniBar
        context={{ ...studioContext, projectId: currentProjectId, runId: runtimeKind === 'run' ? runtimeId : undefined, taskId: runtimeKind === 'task' ? runtimeId : undefined }}
        projectId={currentProjectId}
        snapshot={studioRuntime.snapshot}
        onOpenDetails={run.activeRunId ? () => setShowBrowser(true) : undefined}
      />}
      {showContext&&<div className="lc-studio-context"><div className="lc-toolbar"><strong>{lc('context')}</strong><select aria-label={lc('context')} value={linkedCase?.id??''} onChange={e=>{const item=projectCases.find(c=>c.id===e.target.value);setQuery({...Object.fromEntries(query),caseId:e.target.value});if(item?.binding)void openStudioFile(item.binding.file_path);}}><option value="">{lc('selectCase')}</option>{projectCases.map(item=><option key={item.id} value={item.id}>{item.test_model?.display_id||item.id.slice(-6)} · {item.title}</option>)}</select>{linkedCase&&<><button className="btn btn-secondary btn-sm" onClick={()=>setShowKnowledge(true)}>{lc('inspectKnowledge')}</button>{linkedCase.requirement_id&&<Link className="btn btn-secondary btn-sm" to={`/projects/${currentProjectId}/requirements/${linkedCase.requirement_id}?tab=coverage`}>{lc('riskCoverage')}</Link>}<button className="btn btn-secondary btn-sm" onClick={()=>void openStudioFile('data/shop.json')}>{lc('dataEdit')}</button></>}</div>{linkedCase?.test_model&&<><p className="lc-caption">{linkedCase.test_model.intent} · {Object.values(linkedCase.test_model.coverage).flat().join(' · ')}</p><details><summary>{lc('data')} · {lc('oracles')}</summary><pre>{JSON.stringify({data:linkedCase.test_model.data,oracles:linkedCase.test_model.oracles},null,2)}</pre></details></>}</div>}
      {showCommands&&<CommandPalette onClose={()=>setShowCommands(false)} commands={[{label:lc('runCurrent'),hint:'Ctrl+Enter',run:()=>{void saveAndRun();}},{label:lc('sourceDocument'),hint:'Ctrl+P',run:()=>setShowQuickOpen(true)},{label:lc('showBrowser'),run:()=>setShowBrowser(true)},{label:lc('showAssistant'),run:()=>setShowAssistant(true)},...(linkedCase?[{label:lc('inspectKnowledge'),run:()=>setShowKnowledge(true)}]:[])]}/>}
      {showKnowledge&&linkedCase&&<KnowledgeDrawer projectId={currentProjectId} entityId={linkedCase.id} onClose={()=>setShowKnowledge(false)}/>}
    <div className="studio-container" style={{flex:1,height:'auto',minHeight:0}}>
      {/* Quick Open Dialog (Cmd+P) */}
      {showQuickOpen && (
        <QuickOpen
          files={workspace.allFilePaths}
          query={quickOpenQuery}
          selectedIndex={quickOpenSelectedIndex}
          onQueryChange={setQuickOpenQuery}
          onSelectedIndexChange={setQuickOpenSelectedIndex}
          onSelect={(path) => {
            openStudioFile(path);
            setShowQuickOpen(false);
          }}
          onClose={() => setShowQuickOpen(false)}
        />
      )}

      {/* File Operation Modal */}
      {fileOpModal && (
        <FileOpModal
          state={fileOpModal}
          inputText={opInputText}
          onInputChange={setOpInputText}
          onClose={() => setFileOpModal(null)}
          onConfirm={handleExecuteFileOp}
        />
      )}

      {/* Branch Create Modal */}
      {git.showBranchModal && (
        <BranchModal
          branchName={git.newBranchInput}
          currentBranch={git.currentBranch}
          onBranchNameChange={git.setNewBranchInput}
          onClose={() => git.setShowBranchModal(false)}
          onConfirm={git.handleCreateBranch}
        />
      )}

      {/* Pull Request Create Modal */}
      {git.showPRModal && (
        <PullRequestModal
          currentBranch={git.currentBranch}
          title={git.prTitleInput}
          body={git.prBodyInput}
          suggesting={git.suggestingPR}
          creating={git.creatingPR}
          onTitleChange={git.setPRTitleInput}
          onBodyChange={git.setPRBodyInput}
          onClose={() => git.setShowPRModal(false)}
          onRegenerate={git.handleOpenPRModal}
          onCreate={git.handleCreatePR}
        />
      )}

      {/* Left Sidebar: File Explorer & Test Explorer */}
      <div id="studio-workspace-files" className="studio-sidebar" style={showFiles?undefined:{display:'none'}}>
        {/* Project Selector inside studio */}
        <ProjectSelector
          projects={projects}
          currentProjectId={currentProjectId}
          onSelectProject={onSelectProject}
          onQuickOpen={() => setShowQuickOpen(true)}
          hideProjectSelect={embedded}
        />

        {/* Sidebar View Switcher: Files vs Tests vs Git vs PR */}
        <SidebarViewSwitcher
          sidebarTab={sidebarTab}
          testCount={tests.collectedTests.length}
          changeCount={git.diffResult.changed_files.length}
          activePRNumber={git.activePR ? git.activePR.number : null}
          onSelectTab={handleSelectSidebarTab}
        />

        {/* Action Header */}
        <SidebarActionHeader
          sidebarTab={sidebarTab}
          currentBranch={git.currentBranch}
          activePRNumber={git.activePR ? git.activePR.number : null}
          loadingChecks={git.loadingChecks}
          onNewFile={() => {
            setFileOpModal({ type: 'create_file' });
            setOpInputText('tests/test_example.py');
          }}
          onNewFolder={() => {
            setFileOpModal({ type: 'create_folder' });
            setOpInputText('pages');
          }}
          onNewBranch={() => {
            git.setNewBranchInput(`qa/feature-${Date.now().toString().slice(-4)}`);
            git.setShowBranchModal(true);
          }}
          onRefreshChecks={git.handleRefreshPRChecks}
          onRefreshAll={handleRefreshAll}
        />

        {/* Content Area for 4 Tabs */}
        <div
          id="studio-sidebar-panel"
          className="studio-file-tree"
          role="tabpanel"
          aria-labelledby={`studio-sidebar-tab-${sidebarTab}`}
          tabIndex={0}
        >
          {sidebarTab === 'files' && (
            <FileTree
              files={workspace.files}
              expandedFolders={workspace.expandedFolders}
              activeTabPath={showAutomationSetup ? null : editor.activeTabPath}
              onToggleFolder={workspace.toggleFolder}
              onOpenFile={openSidebarFile}
              onCreateFileInside={(dirPath) => {
                setFileOpModal({ type: 'create_file', targetPath: dirPath });
                setOpInputText(`${dirPath}/new_file.py`);
              }}
              onRename={(path) => {
                setFileOpModal({ type: 'rename', targetPath: path });
                setOpInputText(path);
              }}
              onDelete={(path) => setFileOpModal({ type: 'delete', targetPath: path })}
              onBootstrapWorkspace={handleBootstrapWorkspace}
            />
          )}

          {sidebarTab === 'tests' && (
            <TestExplorer
              tests={tests.collectedTests}
              loading={tests.loadingTests}
              hasCollected={tests.hasCollectedTests}
              collectionFailed={tests.collectionFailed}
              runningTest={run.runningTest}
              onCollect={() => { void tests.fetchCollectedTests(); }}
              onOpenFile={openSidebarFile}
              onRunTest={(nodeid)=>{void saveAndRun(nodeid);}}
              onDebugTest={(nodeid) => { void startDebug(nodeid); }}
            />
          )}

          {sidebarTab === 'git' && (
            <SourceControlPanel
              currentBranch={git.currentBranch}
              branches={git.branches}
              recentCommits={git.recentCommits}
              diffResult={git.diffResult}
              showDiffView={git.showDiffView}
              commitMessage={git.commitMessage}
              isCommitting={git.isCommitting}
              isPushing={git.isPushing}
              pushStatusMessage={git.pushStatusMessage}
              suggestingCommit={git.suggestingCommit}
              onSwitchBranch={git.handleSwitchBranch}
              onNewBranch={() => {
                git.setNewBranchInput(`qa/C12345-suite-${Date.now().toString().slice(-4)}`);
                git.setShowBranchModal(true);
              }}
              onToggleDiffView={() => git.setShowDiffView(!git.showDiffView)}
              onOpenFile={openSidebarFile}
              onCommitMessageChange={git.setCommitMessage}
              onSuggestCommit={git.handleSuggestCommitMessage}
              onCommit={git.handleCommitChanges}
              onPush={git.handlePushBranch}
              onOpenPRModal={git.handleOpenPRModal}
            />
          )}

          {sidebarTab === 'pr' && (
            <PullRequestPanel
              activePR={git.activePR}
              prChecks={git.prChecks}
              loadingChecks={git.loadingChecks}
              diagnosingCheckId={git.diagnosingCheckId}
              ciDiagnosisResult={git.ciDiagnosisResult}
              onOpenPRModal={git.handleOpenPRModal}
              onRefreshChecks={git.handleRefreshPRChecks}
              onDiagnose={git.handleDiagnoseCI}
              onDismissDiagnosis={() => git.setCIDiagnosisResult(null)}
            />
          )}
        </div>
      </div>

      {/* Center Panel: workbench (tabs, tools, editor, problems, status bar) */}
      <div className="studio-editor-pane">
        <div className="studio-editor-tabs">
          <EditorTabs
            tabs={showAutomationSetup ? [] : editor.tabs}
            activeTabPath={showAutomationSetup ? null : editor.activeTabPath}
            showDiffView={!showAutomationSetup && git.showDiffView}
            onSelectTab={editor.selectTab}
            onCloseTab={editor.closeTab}
          />

          <div className="studio-toolbar-group no-chrome">
            {!showAutomationSetup && editor.activeTab && (
              <button className="studio-tool" disabled={!editor.activeTab.isDirty || editor.saving} onClick={editor.saveActiveTab} title={t('editor.saveCurrentFile')}>
                <Save size={14} />
                {editor.saving ? t('editor.saving') : t('common:save')}
              </button>
            )}
            {!showAutomationSetup && <button
              className="studio-tool"
              onClick={problems.validateWorkspace}
              disabled={problems.validating}
              title={t('editor.validateTooltip')}
            >
              <CheckCircle2 size={14} color={problems.validationFailed ? 'var(--ui-rose-strong)' : !problems.hasValidated ? 'var(--ink-muted)' : problemCount === 0 ? 'var(--ui-mint-strong)' : 'var(--ui-rose)'} />
              {problems.validating ? t('editor.checking') : t('editor.problemsShort')}
              <span className={`studio-tool-count ${problemCount > 0 ? 'has-issues' : ''}`}>
                {problemCount || (problems.hasValidated ? 0 : '—')}
              </span>
            </button>}
            {editor.activeTab && (editor.activeTab.path.includes('test_') || editor.activeTab.path.endsWith('.py')) && (
              <button
                className="studio-tool is-primary"
                disabled={run.runningTest || debug.state === 'starting' || debug.state === 'running' || debug.state === 'paused'}
                onClick={() => {void saveAndRun();}}
                title={debug.state === 'starting' || debug.state === 'running' || debug.state === 'paused'
                  ? t('editor.debugActive')
                  : t('editor.runFileTooltip')}
              >
                <Play size={14} />
                {run.runningTest ? t('editor.running') : t('editor.runFile')}
              </button>
            )}
            {!showAutomationSetup && <button
              className="studio-tool"
              disabled={!debugTargetNodeId || run.runningTest || debug.state === 'starting' || debug.state === 'running' || debug.state === 'paused'}
              onClick={async () => {
                if (!debugTargetNodeId) return;
                await startDebug(debugTargetNodeId);
              }}
              title={debugTargetNodeId ? t('editor.debugTarget', { nodeid: debugTargetNodeId }) : t('editor.noDebugTarget')}
            >
              <Bug size={14} />
              {debug.state === 'starting' ? t('debug.starting') : t('editor.debugTest')}
            </button>}
            {(debug.state === 'running' || debug.state === 'paused') && (
              <div className="studio-toolbar-group no-chrome" role="group" aria-label={t('debug.controls')}>
                {debug.state === 'paused' ? (
                  <>
                    <button className="studio-tool is-primary" onClick={() => debug.control('continue')}>{t('debug.continue')}</button>
                    <button className="studio-tool" onClick={() => debug.control('next')}>{t('debug.stepOver')}</button>
                    <button className="studio-tool" onClick={() => debug.control('stepIn')}>{t('debug.stepIn')}</button>
                    <button className="studio-tool" onClick={() => debug.control('stepOut')}>{t('debug.stepOut')}</button>
                  </>
                ) : (
                  <button className="studio-tool" onClick={() => debug.control('pause')}>{t('debug.pause')}</button>
                )}
                <button className="studio-tool" onClick={() => { void debug.stop(); }}>{t('debug.stop')}</button>
              </div>
            )}
          </div>
        </div>

        {/* Editor or Diff View Area */}
        <div className="studio-editor-surface">
        {showAutomationSetup ? <section className="workspace-automation-empty">
          <FileCode2 size={36} aria-hidden="true" />
          <strong>{t(workspaceAutomationSetup === 'no-case' ? 'editor.noCaseTitle' : 'editor.unboundTitle')}</strong>
          <p>{t(workspaceAutomationSetup === 'no-case' ? 'editor.noCaseHint' : 'editor.unboundHint')}</p>
          <div>
            {workspaceAutomationSetup === 'no-case' ? <button type="button" className="btn btn-primary btn-sm" onClick={onSelectCases}>{t('editor.openCases')}</button> : <>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => {
                setFileOpModal({ type: 'create_file' });
                setOpInputText(`tests/test_${workspaceAutomationSetupKey?.replace(/[^a-zA-Z0-9_-]/g, '_')}.py`);
              }}>{t('editor.createScript')}</button>
              <button type="button" className="btn btn-primary btn-sm" onClick={onStartRecording}>{t('editor.recordScript')}</button>
            </>}
          </div>
        </section> : <MonacoEditorPane
          projectId={currentProjectId}
          onNavigateToSource={async (path, line) => { await openStudioFile(path); setSourceFocus({ path, line }); }}
          onAIAction={(action) => { void assistant.sendMessage(t(`lsp.requests.${action}`)); }}
          onLanguageDiagnostics={(uri, diagnostics) => {
            const path = decodeURIComponent(new URL(uri).pathname).replace(/^\//, '');
            setLanguageIssues((items) => ({ ...items, [path]: diagnostics.map((item) => ({
              file: path, line: item.range.start.line + 1, column: item.range.start.character + 1,
              message: item.message, severity: item.severity === 1 ? 'error' : item.severity === 2 ? 'warning' : 'info', rule_id: 'basedpyright',
            })) }));
          }}
          activeTab={editor.activeTab}
          loadingFile={workspace.loadingFile}
          showDiffView={git.showDiffView}
          diffResult={git.diffResult}
          editorRef={editorRef}
          onChange={editor.updateContent}
          breakpoints={breakpoints}
          onToggleBreakpoint={toggleBreakpoint}
          initialFocusLineNumber={sourceFocus && sourceFocus.path === editor.activeTab?.path ? sourceFocus.line : initialOpenLineNumber ?? undefined}
          executionLocation={executionLocation}
        />}

        </div>

        {(preset === 'debug' || debug.state !== 'idle' || initialDebugNodeId || debugPreparationError) && (
          <DebugPanel
            state={debugPreparationError ? 'error' : debug.state}
            nodeid={debug.targetNodeid}
            error={debugPreparationError || debug.error}
            frames={debug.frames}
            locals={debug.locals}
            output={debug.output}
            breakpointBindings={debug.breakpointBindings}
            hasHitBreakpoint={debug.hasHitBreakpoint}
            onSelectFrame={debug.selectFrame}
          />
        )}

        {/* Resizable, collapsible bottom dock: problems + quick run output */}
        <div
          className={`studio-bottom-panels${problems.showProblemsPanel ? '' : ' is-collapsed'}`}
          style={{ borderTop: '1px solid var(--ui-line)', background: 'var(--ui-surface-raised)', '--studio-dock-height': `${bottomDock.size}px` } as React.CSSProperties}
        >
          <div
            className="studio-dock-resize"
            aria-label={t('bottomDock.resizePanel')}
            title={t('bottomDock.resizePanel')}
            {...bottomDock.handleProps}
          />
          <ProblemsPanel
            issues={[...problems.validationIssues, ...Object.values(languageIssues).flat()]}
            expanded={problems.showProblemsPanel}
            validating={problems.validating}
            hasValidated={problems.hasValidated}
            validationFailed={problems.validationFailed}
            onToggle={() => problems.setShowProblemsPanel(!problems.showProblemsPanel)}
            onValidate={() => { void problems.validateWorkspace(); }}
            onJumpToIssue={problems.jumpToIssue}
          />

          {/* Quick Execution Log notification bar */}
          <div className="studio-dock-runoutput">
            <RunOutputPanel lastRunResult={run.lastRunResult} runId={run.activeRunId} onNavigateToRuns={onNavigateToRuns} />
          </div>
        </div>

        <WorkbenchStatusBar
          branch={git.currentBranch}
          problemCount={problemCount}
          validating={problems.validating}
          hasValidated={problems.hasValidated}
          validationFailed={problems.validationFailed}
          runningTest={run.runningTest}
          saving={editor.saving}
          activeFileName={showAutomationSetup ? null : editor.activeTab?.path ?? null}
          language={!showAutomationSetup && editor.activeTab ? (editor.activeTab.path.split('.').pop() ?? null) : null}
        />
      </div>

      {/* On-demand live browser and run drawer */}
      {showBrowser&&<div className="lc-studio-run-overlay" onKeyDownCapture={handleBrowserDrawerKeyDown}>
        <button type="button" className="lc-studio-run-backdrop" tabIndex={-1} aria-label={lc('closeRunDrawer')} onClick={closeBrowserDrawer}/>
        <aside ref={browserDrawerRef} className="lc-studio-run-drawer" id="studio-run-drawer" role="dialog" aria-modal="true" aria-label={lc('runtimeDrawer')} tabIndex={-1}>
          <StudioRunPanel key={currentProjectId} runId={run.activeRunId} projectId={currentProjectId} context={{...studioContext,file:editor.activeTab?.path??studioContext.file}} onClose={closeBrowserDrawer} onStep={async(path,line)=>{await openStudioFile(path);setSourceFocus({path,line});}}/>
        </aside>
      </div>}
      {showAssistant&&<QAAssistantPanel
        messages={assistant.assistantMessages}
        input={assistant.assistantInput}
        loading={assistant.assistantLoading}
        traceEvents={assistant.assistantTraceEvents}
        onInputChange={assistant.setAssistantInput}
        onSend={assistant.sendMessage}
        onCancel={assistant.cancelStream}
        onInsertSnippet={assistant.insertSnippet}
        onStartGenerateTask={(url, goal) => {
          if (!currentProjectId) return;
          void generateTask.start({ type: 'CREATE_TEST', goal, project_id: currentProjectId, workspace_id: currentProjectId, inputs: { ...(url?{url}:{}), requirement: goal, ...(linkedCase?{test_case_id:linkedCase.id}:{}) } });
        }}
        generateTask={generateTask.task}
        generateTaskBusy={generateTask.busy}
        generateTaskError={generateTask.error}
      />}
    </div>
    </div>
  );
};
