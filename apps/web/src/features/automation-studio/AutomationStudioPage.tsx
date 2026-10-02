import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bug, CheckCircle2, Play, Save } from 'lucide-react';
import { api } from '../../api/client';
import { Breakpoint, Project, TestCase } from '../../types';
import { Link, useSearchParams } from 'react-router-dom';
import { KnowledgeDrawer } from '../lifecycle/KnowledgeDrawer';
import { StudioRunPanel } from '../lifecycle/StudioRunPanel';
import { CommandPalette } from '../lifecycle/CommandPalette';
import '../lifecycle/lifecycle.css';
import { FileOpModalState, SidebarTab } from './types';
import { errorText } from './errorText';
import { useWorkspaceFiles } from './hooks/useWorkspaceFiles';
import { useEditorTabs } from './hooks/useEditorTabs';
import { useWorkspaceGit } from './hooks/useWorkspaceGit';
import { useTestExplorer } from './hooks/useTestExplorer';
import { useProblems } from './hooks/useProblems';
import { useQAAssistant } from './hooks/useQAAssistant';
import { useRunExecution } from './hooks/useRunExecution';
import { useDebugSession, type DebugStackFrame } from './hooks/useDebugSession';
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

export interface AutomationStudioPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onSelectProject: (id: string) => void;
  onNavigateToRuns?: (runId?: string) => void;
  initialOpenFilePath?: string | null;
  initialOpenLineNumber?: number | null;
  initialDebugNodeId?: string | null;
}

export const AutomationStudioPage: React.FC<AutomationStudioPageProps> = ({
  projects,
  selectedProjectId,
  onSelectProject,
  onNavigateToRuns,
  initialOpenFilePath,
  initialOpenLineNumber,
  initialDebugNodeId,
}) => {
  const { t } = useTranslation('studioShell');
  const { t: lc } = useTranslation('lifecycle');
  const [query,setQuery] = useSearchParams();
  const [showBrowser,setShowBrowser]=useState(false);
  const [showAssistant,setShowAssistant]=useState(false);
  const [showContext,setShowContext]=useState(true);
  const [showFiles,setShowFiles]=useState(true);
  const [showCommands,setShowCommands]=useState(false);
  const [showKnowledge,setShowKnowledge]=useState(false);
  const [projectCases,setProjectCases]=useState<TestCase[]>([]);
  const preset=query.get('preset')??'code';
  const currentProjectId = selectedProjectId || projects[0]?.id || null;
  useEffect(()=>{let disposed=false;setProjectCases([]);if(currentProjectId)api.getTestCases(currentProjectId).then(items=>{if(!disposed)setProjectCases(items);}).catch(()=>{});return()=>{disposed=true;};},[currentProjectId]);
  useEffect(()=>{setShowBrowser(preset==='record'||currentProjectId==='proj_golden_shop_v1');setShowAssistant(preset==='review');setShowContext(true);setShowFiles(preset!=='debug');},[preset,currentProjectId]);
  const generateTask = useContextTask(currentProjectId, 'studio', currentProjectId);

  // Cross-panel UI state (read/written by more than one panel)
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>('files');
  const [fileOpModal, setFileOpModal] = useState<FileOpModalState | null>(null);
  const [opInputText, setOpInputText] = useState<string>('');
  const [showQuickOpen, setShowQuickOpen] = useState<boolean>(false);
  const [quickOpenQuery, setQuickOpenQuery] = useState<string>('');
  const [quickOpenSelectedIndex, setQuickOpenSelectedIndex] = useState<number>(0);
  const [breakpoints, setBreakpoints] = useState<Breakpoint[]>([]);
  const [debugPreparationError, setDebugPreparationError] = useState('');
  const [sourceFocus, setSourceFocus] = useState<{ path: string; line: number } | null>(null);
  const [languageIssues, setLanguageIssues] = useState<Record<string, import('../../types').ValidationIssue[]>>({});
  useEffect(() => { setLanguageIssues({}); }, [currentProjectId]);
  const [executionLocation, setExecutionLocation] = useState<{ path: string; line: number } | null>(null);

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
  const assistant = useQAAssistant({
    projectId: currentProjectId,
    activeTab: editor.activeTab,
    editorRef,
    onInsertFallback: editor.updateContent,
    caseId: query.get('caseId'),
  });
  const run = useRunExecution({ projectId: currentProjectId, activeTabPath: editor.activeTabPath, onNavigateToRuns });
  useEffect(()=>{if(run.activeRunId)setShowBrowser(true);},[run.activeRunId]);
  const linkedCase=projectCases.find(item=>item.id===query.get('caseId'));
  const selectedTarget=linkedCase?.binding?.file_path===editor.activeTabPath?linkedCase.binding.nodeid:undefined;
  const saveAndRun=async(target?:string)=>{if(!editor.activeTabPath&&!target){setDebugPreparationError(lc('noSourceFile'));return;}if(await editor.saveAll())await run.runExecution(target??selectedTarget??editor.activeTabPath??undefined);};
  const runCurrentRef=useRef(saveAndRun);runCurrentRef.current=saveAndRun;
  const debug = useDebugSession({
    projectId: currentProjectId,
    breakpoints,
    onOpenFile: editor.openFile,
    onExecutionLine: setExecutionLocation,
    onBreakpoints: (sessionBreakpoints) => {
      setBreakpoints((items) => [
        ...items.filter((item) => !sessionBreakpoints.some((sessionBreakpoint) => sessionBreakpoint.id === item.id)),
        ...sessionBreakpoints,
      ]);
    },
  });
  const startDebug = async (nodeid: string) => {
    setDebugPreparationError('');
    if (!await editor.saveAll()) {
      setDebugPreparationError(t('debug.saveFailed', { ns: 'studioPanels' }));
      return;
    }
    await debug.start(nodeid);
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

  fetchFilesRef.current = workspace.fetchFiles;
  openFileRef.current = editor.openFile;

  useEffect(() => {
    workspace.fetchFiles();
    tests.fetchCollectedTests();
    problems.validateWorkspace();
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
    if (initialOpenFilePath) {
      editor.openFile(initialOpenFilePath);
    }
  }, [initialOpenFilePath]);

  useEffect(() => {
    if (!initialDebugNodeId || !currentProjectId) return;
    const target = currentProjectId + '::' + initialDebugNodeId;
    if (autoDebugStartedRef.current === target) return;
    autoDebugStartedRef.current = target;
    void debugStartRef.current(initialDebugNodeId);
  }, [currentProjectId, initialDebugNodeId]);

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
    if (tab === 'tests') tests.fetchCollectedTests();
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
        editor.openFile(input);
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

  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%',minHeight:0}}>
      <div className="lc-preset-bar"><Link to={`/projects/${currentProjectId}`}>{projects.find(p=>p.id===currentProjectId)?.name}</Link><span>/ Studio</span>{linkedCase&&<Link to={`/projects/${currentProjectId}/test-cases/${linkedCase.id}`}>{linkedCase.test_model?.display_id||linkedCase.title}</Link>}
        <span className="lc-muted">{lc('preset')}</span>{['code','debug','review'].map(view=><button key={view} className={`btn btn-sm ${preset===view?'btn-primary':'btn-secondary'}`} onClick={()=>setQuery({...Object.fromEntries(query),preset:view})}>{view==='code'?'Code':view==='debug'?'Debug':'Review'}</button>)}
        <button className="btn btn-secondary btn-sm" onClick={()=>setShowFiles(v=>!v)} aria-pressed={showFiles}>{lc('sourceDocument')}</button><button className="btn btn-secondary btn-sm" onClick={()=>setShowContext(v=>!v)} aria-pressed={showContext}>{lc('context')}</button><button className="btn btn-secondary btn-sm" onClick={()=>setShowBrowser(v=>!v)} aria-pressed={showBrowser}>{lc('browser')}</button><button className="btn btn-secondary btn-sm" onClick={()=>setShowAssistant(v=>!v)} aria-pressed={showAssistant}>{lc('assistant')}</button><button className="btn btn-secondary btn-sm" onClick={()=>setShowCommands(true)}>{lc('commands')} ⌃K</button>
      </div>
      {showContext&&<div className="lc-studio-context"><div className="lc-toolbar"><strong>{lc('context')}</strong><select aria-label={lc('context')} value={linkedCase?.id??''} onChange={e=>{const item=projectCases.find(c=>c.id===e.target.value);setQuery({...Object.fromEntries(query),caseId:e.target.value});if(item?.binding)void editor.openFile(item.binding.file_path);}}><option value="">{lc('selectCase')}</option>{projectCases.map(item=><option key={item.id} value={item.id}>{item.test_model?.display_id||item.id.slice(-6)} · {item.title}</option>)}</select>{linkedCase&&<><button className="btn btn-secondary btn-sm" onClick={()=>setShowKnowledge(true)}>{lc('inspectKnowledge')}</button>{linkedCase.requirement_id&&<Link className="btn btn-secondary btn-sm" to={`/projects/${currentProjectId}/requirements/${linkedCase.requirement_id}?tab=coverage`}>{lc('riskCoverage')}</Link>}<button className="btn btn-secondary btn-sm" onClick={()=>void editor.openFile('data/shop.json')}>{lc('dataEdit')}</button></>}</div>{linkedCase?.test_model&&<><p className="lc-caption">{linkedCase.test_model.intent} · {Object.values(linkedCase.test_model.coverage).flat().join(' · ')}</p><details><summary>{lc('data')} · {lc('oracles')}</summary><pre>{JSON.stringify({data:linkedCase.test_model.data,oracles:linkedCase.test_model.oracles},null,2)}</pre></details></>}</div>}
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
            editor.openFile(path);
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
      <div className="studio-sidebar" style={showFiles?undefined:{display:'none'}}>
        {/* Project Selector inside studio */}
        <ProjectSelector
          projects={projects}
          currentProjectId={currentProjectId}
          onSelectProject={onSelectProject}
          onQuickOpen={() => setShowQuickOpen(true)}
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
        <div className="studio-file-tree">
          {sidebarTab === 'files' && (
            <FileTree
              files={workspace.files}
              expandedFolders={workspace.expandedFolders}
              activeTabPath={editor.activeTabPath}
              onToggleFolder={workspace.toggleFolder}
              onOpenFile={editor.openFile}
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
              runningTest={run.runningTest}
              onOpenFile={editor.openFile}
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
              onOpenFile={editor.openFile}
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
            tabs={editor.tabs}
            activeTabPath={editor.activeTabPath}
            showDiffView={git.showDiffView}
            onSelectTab={editor.selectTab}
            onCloseTab={editor.closeTab}
          />

          <div className="studio-toolbar-group no-chrome">
            {editor.activeTab && (
              <button className="studio-tool" disabled={!editor.activeTab.isDirty || editor.saving} onClick={editor.saveActiveTab} title={t('editor.saveCurrentFile')}>
                <Save size={14} />
                {editor.saving ? t('editor.saving') : t('common:save')}
              </button>
            )}
            <button
              className="studio-tool"
              onClick={problems.validateWorkspace}
              disabled={problems.validating}
              title={t('editor.validateTooltip')}
            >
              <CheckCircle2 size={14} color={problems.validationIssues.length + Object.values(languageIssues).flat().length === 0 ? 'var(--ui-mint-strong)' : 'var(--ui-rose)'} />
              {t('editor.problemsShort')}
              <span className={`studio-tool-count ${problems.validationIssues.length > 0 ? 'has-issues' : ''}`}>
                {problems.validationIssues.length + Object.values(languageIssues).flat().length}
              </span>
            </button>
            {editor.activeTab && (editor.activeTab.path.includes('test_') || editor.activeTab.path.endsWith('.py')) && (
              <button
                className="studio-tool is-primary"
                disabled={run.runningTest}
                onClick={() => {void saveAndRun();}}
                title={t('editor.runTestTooltip')}
              >
                <Play size={14} />
                {run.runningTest ? t('editor.running') : t('editor.runTest')}
              </button>
            )}
            <button
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
            </button>
            {(debug.state === 'running' || debug.state === 'paused') && (
              <div className="studio-toolbar-group no-chrome" aria-label={t('debug.controls')}>
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
        <MonacoEditorPane
          projectId={currentProjectId}
          onNavigateToSource={async (path, line) => { await editor.openFile(path); setSourceFocus({ path, line }); }}
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
        />

        </div>

        {(debug.state !== 'idle' || initialDebugNodeId || debugPreparationError) && (
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

        {/* Collapsible Bottom Problems Panel */}
        <div style={{ borderTop: '1px solid var(--ui-line)', background: 'var(--ui-surface-raised)' }}>
          <ProblemsPanel
            issues={[...problems.validationIssues, ...Object.values(languageIssues).flat()]}
            expanded={problems.showProblemsPanel}
            onToggle={() => problems.setShowProblemsPanel(!problems.showProblemsPanel)}
            onJumpToIssue={problems.jumpToIssue}
          />

          {/* Quick Execution Log notification bar */}
          <RunOutputPanel lastRunResult={run.lastRunResult} onNavigateToRuns={onNavigateToRuns} />
        </div>

        <WorkbenchStatusBar
          branch={git.currentBranch}
          problemCount={problems.validationIssues.length + Object.values(languageIssues).flat().length}
          validating={problems.validating}
          runningTest={run.runningTest}
          saving={editor.saving}
          activeFileName={editor.activeTab?.path ?? null}
          language={editor.activeTab ? (editor.activeTab.path.split('.').pop() ?? null) : null}
        />
      </div>

      {/* Right Panel: Interactive QA Assistant Sidecar */}
      {showBrowser&&<aside className="lc-studio-preview"><StudioRunPanel key={currentProjectId} runId={run.activeRunId} projectId={currentProjectId} onStep={async(path,line)=>{await editor.openFile(path);setSourceFocus({path,line});}}/></aside>}
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
