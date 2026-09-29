import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowDown, ArrowUp, CirclePause, CirclePlay, Code2, Crosshair, MousePointer2, RotateCw, Save, Square, Trash2 } from 'lucide-react';
import { api, getRecorderSocketUrl } from '../api/client';
import { MonacoEditorPane, MonacoEditorInstance } from '../features/automation-studio/components/MonacoEditorPane';
import { EditorTab } from '../features/automation-studio/types';
import { GitDiffResult, Project, RecorderStep, TestCasePriority } from '../types';

type StepAction = RecorderStep['action'];
type Frame = { type: string; image?: string; url?: string; title?: string; state?: string; steps?: RecorderStep[]; tabs?: Array<{index:number;url:string;title:string;active:boolean}>; picked?: { action: string; name?: string; frame_path?: string[]; ranked_candidates?: RecorderStep['locator'][] } | null; message?: string };

const actions: StepAction[] = ['navigate','click','double_click','fill','select','check','uncheck','press','hover','wait','assert_visible','assert_text','assert_url','assert_title','assert_count'];
const labels: Record<StepAction, string> = { navigate:'打开页面', click:'点击', double_click:'双击', fill:'填写', select:'选择', check:'勾选', uncheck:'取消勾选', press:'按键', hover:'悬停', wait:'等待', assert_visible:'断言可见', assert_text:'断言文本', assert_url:'断言 URL', assert_title:'断言标题', assert_count:'断言数量' };
const blankDiff: GitDiffResult = { diff: '', changed_files: [] };

export const RecorderPage: React.FC<{ projects: Project[]; selectedProjectId: string | null }> = ({ projects, selectedProjectId }) => {
  const navigate = useNavigate();
  const projectId = selectedProjectId ?? projects[0]?.id ?? null;
  const [url, setUrl] = useState('https://example.com');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [restoreCheckedProjectId, setRestoreCheckedProjectId] = useState<string | null>(null);
  const [socketState, setSocketState] = useState('未连接');
  const [frame, setFrame] = useState<Frame | null>(null);
  const [steps, setSteps] = useState<RecorderStep[]>([]);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [caseName, setCaseName] = useState('录制的浏览器用例');
  const [filePath, setFilePath] = useState('tests/test_recorded_case.py');
  const [testName, setTestName] = useState('test_recorded_case');
  const [suiteName, setSuiteName] = useState('录制用例');
  const [tagsText, setTagsText] = useState('recorder');
  const [markersText, setMarkersText] = useState('');
  const [code, setCode] = useState('');
  const [editorReady, setEditorReady] = useState(false);
  const [showCodeFallback, setShowCodeFallback] = useState(false);
  const [pickTargetStep, setPickTargetStep] = useState<string | null>(null);
  const pickTargetStepRef = useRef<string | null>(null);
  const [priority, setPriority] = useState<TestCasePriority>('P2');
  const wsRef = useRef<WebSocket | null>(null);
  const browserRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<MonacoEditorInstance | null>(null);
  const stepStorageKey = sessionId ? `ai-qa.recorder.steps.${sessionId}` : '';
  const projectStepsKey = projectId ? `ai-qa.recorder.draft-steps.${projectId}` : '';
  const projectCodeKey = projectId ? `ai-qa.recorder.code.${projectId}` : '';
  const tab = useMemo<EditorTab | undefined>(() => code ? ({ path: filePath, name: filePath.split('/').pop() || 'test.py', content: code, initialContent: code, isDirty: false }) : undefined, [code, filePath]);

  useEffect(() => {
    if (!code) { setEditorReady(false); setShowCodeFallback(false); return; }
    setShowCodeFallback(false);
    const timer = window.setTimeout(() => { if (!editorRef.current) setShowCodeFallback(true); }, 2500);
    return () => window.clearTimeout(timer);
  }, [code]);

  useEffect(() => {
    if (!projectId || sessionId) return;
    try {
      const savedSteps = window.localStorage.getItem(`ai-qa.recorder.draft-steps.${projectId}`);
      if (savedSteps) setSteps(JSON.parse(savedSteps) as RecorderStep[]);
      const savedCode = window.localStorage.getItem(`ai-qa.recorder.code.${projectId}`);
      if (savedCode) setCode(savedCode);
    } catch { /* ignore damaged local drafts and restore the session below */ }
    const storedId = window.localStorage.getItem(`ai-qa.recorder.session.${projectId}`);
    if (!storedId) { setRestoreCheckedProjectId(projectId); return; }
    try {
      const savedSteps = window.localStorage.getItem(`ai-qa.recorder.steps.${storedId}`);
      if (savedSteps) setSteps(JSON.parse(savedSteps) as RecorderStep[]);
    } catch { /* ignore damaged local drafts and restore the session below */ }
    let active = true;
    api.getRecorderSession(storedId).then((saved) => {
      if (!active || saved.project_id !== projectId) return;
      setSessionId(saved.id);
      setSteps(saved.steps);
      setUrl(saved.url);
      setRecording(saved.state === 'RECORDING');
    }).catch(() => window.localStorage.removeItem(`ai-qa.recorder.session.${projectId}`)).finally(() => { if (active) setRestoreCheckedProjectId(projectId); });
    return () => { active = false; };
  }, [projectId, sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    const ws = new WebSocket(getRecorderSocketUrl(sessionId));
    wsRef.current = ws;
    ws.onopen = () => { setSocketState('已连接'); setError(''); };
    ws.onclose = (event) => { setSocketState(event.code === 1000 ? '已关闭' : `连接中断 (${event.code})`); };
    ws.onerror = () => setSocketState('连接错误');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as Frame;
      if (data.type === 'frame') {
        setFrame(data);
        if (data.steps) setSteps(data.steps);
        if (data.picked && pickTargetStepRef.current) {
          const best = data.picked.ranked_candidates?.[0];
          if (best) {
            setCode('');
            setSteps((current) => current.map((step) => {
              if (step.id !== pickTargetStepRef.current) return step;
              const updated = { ...step, locator: best, frame_path: data.picked?.frame_path || [] };
              send('edit_step', { step: updated });
              return updated;
            }));
          }
          pickTargetStepRef.current = null;
          setPickTargetStep(null);
        }
        if (data.url) setUrl(data.url);
        if (data.state) setRecording(data.state === 'RECORDING');
      } else if (data.type === 'error' || data.type === 'command_error') setError(data.message || '浏览器操作失败');
    };
    return () => { ws.close(); if (wsRef.current === ws) wsRef.current = null; };
  }, [sessionId]);

  useEffect(() => {
    if (!projectId) return;
    const key = `ai-qa.recorder.session.${projectId}`;
    if (sessionId) window.localStorage.setItem(key, sessionId);
  }, [projectId, sessionId]);

  useEffect(() => {
    if (!stepStorageKey) return;
    try { window.localStorage.setItem(stepStorageKey, JSON.stringify(steps)); } catch { /* keep current editor state */ }
  }, [steps, stepStorageKey]);

  useEffect(() => {
    if (!projectId || restoreCheckedProjectId !== projectId || !projectStepsKey) return;
    try { window.localStorage.setItem(projectStepsKey, JSON.stringify(steps)); } catch { /* local recovery is best effort */ }
  }, [steps, projectId, projectStepsKey, restoreCheckedProjectId]);

  useEffect(() => {
    if (projectCodeKey && code) window.localStorage.setItem(projectCodeKey, code);
  }, [code, projectCodeKey]);

  const send = useCallback((action: string, payload: Record<string, unknown> = {}) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action, ...payload }));
  }, []);

  const createSession = async () => {
    if (!projectId) { setError('请先创建或选择项目'); return; }
    setBusy(true); setError('');
    try {
      const created = await api.createRecorderSession(projectId, url, steps);
      setSessionId(created.id); setRecording(false);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const closeSession = async () => {
    if (sessionId) { try { await api.closeRecorderSession(sessionId); } catch { /* session may already have ended */ } }
    if (projectId) window.localStorage.removeItem(`ai-qa.recorder.session.${projectId}`);
    wsRef.current?.close(1000); setSessionId(null); setFrame(null); setRecording(false);
  };

  const navigateBrowser = (target: string) => {
    const normalized = /^(https?:|about:)/i.test(target) ? target : `https://${target}`;
    setUrl(normalized); send('navigate', { url: normalized });
  };

  const browserKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) send('type', { text: event.key });
    else if (['Enter','Tab','Escape','Backspace','Delete','ArrowDown','ArrowUp','ArrowLeft','ArrowRight',' '].includes(event.key)) { event.preventDefault(); send('press', { key: event.key === ' ' ? 'Space' : event.key }); }
  };

  const browserClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const scale = Math.min(bounds.width / 1280, bounds.height / 720);
    const offsetX = (bounds.width - 1280 * scale) / 2;
    const offsetY = 0;
    send(event.detail > 1 ? 'double_click' : 'click', { x: (event.clientX - bounds.left - offsetX) / scale, y: (event.clientY - bounds.top - offsetY) / scale });
    event.currentTarget.focus();
  };

  const updateStep = (index: number, patch: Partial<RecorderStep>) => setSteps((current) => current.map((step, i) => {
    if (i !== index) return step;
    const updated = { ...step, ...patch };
    send('edit_step', { step: updated });
    return updated;
  }));
  const addAssertion = (action: StepAction) => {
    const step: RecorderStep = { id: crypto.randomUUID().replaceAll('-', '').slice(0,12), action, description: labels[action], locator: action.startsWith('assert_') && !['assert_url','assert_title'].includes(action) ? { kind:'css', value:'#result', exact:false } : undefined, value: action === 'assert_count' ? '1' : '' };
    setSteps((current) => [...current, step]); send('add_step', { step });
  };

  const generate = async () => {
    if (!sessionId) return;
    setBusy(true); setError('');
    try {
      const result = await api.generateRecorderCode(sessionId, { case_name: caseName, file_path: filePath, test_name: testName, steps });
      setCode(result.code);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const saveAndRun = async () => {
    if (!projectId || !sessionId) return;
    if (!code.trim()) { await generate(); return; }
    setBusy(true); setError('');
    try {
      const normalizedPath = filePath.replaceAll('\\', '/').replace(/^\/+/, '');
      if (!normalizedPath.endsWith('.py') || normalizedPath.split('/').includes('..')) throw new Error('请输入项目内的 .py 文件路径');
      await api.writeWorkspaceFile(projectId, normalizedPath, code);
      const tags = [...new Set([...tagsText.split(',').map((tag)=>tag.trim()).filter(Boolean), ...(suiteName.trim() ? [`suite:${suiteName.trim()}`] : [])])];
      const createdCase = await api.createTestCase({ project_id: projectId, title: caseName, steps: steps.map((step) => step.description || labels[step.action]), expected_result: '所有录制步骤及断言执行通过', priority, automation_status: 'AUTOMATED', tags });
      const normalizedTestName = testName.replace(/\W+/g, '_').replace(/^_+|_+$/g, '') || 'test_recorded_case';
      const safeTestName = normalizedTestName.startsWith('test_') ? normalizedTestName : `test_${normalizedTestName}`;
      const nodeid = `${normalizedPath}::${safeTestName}`;
      await api.saveAutomationBinding(createdCase.id, { test_case_id: createdCase.id, workspace_id: projectId, nodeid, file_path: normalizedPath, framework: 'playwright_python', status: 'ACTIVE' });
      const markers = markersText.split(',').map((marker)=>marker.trim()).filter(Boolean);
      const run = await api.createTestRun({ project_id: projectId, workspace_id: projectId, nodeids: [nodeid], markers, runner_type: 'LOCAL' });
      navigate(`/runs/${run.id}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const actionInputs = (step: RecorderStep, index: number) => {
    const locatorRequired = !['navigate','wait','assert_url','assert_title'].includes(step.action);
    const locatorValue = step.locator?.value ?? '';
    const parameter = step.action === 'navigate' ? step.url ?? '' : step.action === 'press' ? step.key ?? '' : step.value ?? '';
    return <>
      <input aria-label="步骤定位器" value={locatorValue} placeholder={locatorRequired ? '定位器' : '无定位器'} disabled={!locatorRequired} onChange={(e) => updateStep(index, { locator: { ...(step.locator || {kind:'text', exact:true}), value:e.target.value } })} />
      <input aria-label="步骤参数" value={parameter} placeholder={step.action==='wait'?'毫秒':step.action==='assert_count'?'数量':'参数 / 断言值'} onChange={(e) => updateStep(index, step.action==='navigate' ? {url:e.target.value} : step.action==='press' ? {key:e.target.value} : {value:e.target.value})} />
    </>;
  };

  return <div style={{height:'calc(100vh - 72px)', minHeight:650, display:'flex', flexDirection:'column', gap:12, padding:16, color:'var(--text-primary)'}}>
    <header style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
      <div style={{fontSize:20,fontWeight:700,display:'flex',alignItems:'center',gap:8}}><MousePointer2 size={20}/> 浏览器录制器</div>
      <span style={{fontSize:12,color:'var(--text-muted)'}}>会话：{socketState}</span>
      <div style={{flex:1}} />
      <button disabled={busy || !sessionId} onClick={()=>{const next=!recording;setRecording(next);send(recording?'pause':'start')}}>{recording?<CirclePause size={16}/>:<CirclePlay size={16}/>} {recording?'暂停录制':'开始录制'}</button>
      <button disabled={!sessionId} onClick={()=>{send('stop');setRecording(false)}}><Square size={15}/>停止</button>
      <button disabled={!sessionId || busy} onClick={generate}><Code2 size={16}/>生成脚本</button>
      <button disabled={!sessionId || busy || !code} onClick={saveAndRun}><Save size={16}/>保存为 Case 并运行</button>
    </header>
    {error && <div role="alert" style={{padding:10,borderRadius:6,background:'#fee2e2',color:'#991b1b'}}>{error}</div>}
    <div style={{display:'flex',gap:8}}>
      <input value={url} onChange={(e)=>setUrl(e.target.value)} onKeyDown={(e)=>e.key==='Enter'&&navigateBrowser(url)} placeholder="输入网址" style={{flex:1}} />
      <button disabled={!sessionId} onClick={()=>send('back')}>←</button><button disabled={!sessionId} onClick={()=>send('forward')}>→</button>
      <button disabled={!sessionId} onClick={()=>send('reload')} aria-label="刷新"><RotateCw size={16}/></button>
      {!sessionId ? <button disabled={busy || restoreCheckedProjectId !== projectId} onClick={createSession}>启动浏览器</button> : <button onClick={closeSession}>关闭浏览器</button>}
    </div>
    <div style={{flex:1,minHeight:0,display:'grid',gridTemplateColumns:'minmax(400px,1.15fr) minmax(380px,0.85fr)',gap:12}}>
      <section style={{display:'flex',flexDirection:'column',minHeight:0,border:'1px solid var(--border-color)',borderRadius:8,overflow:'hidden'}}>
        <div style={{padding:'8px 12px',fontSize:12,background:'var(--surface-secondary)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{frame?.title || '远程浏览器画面'} · {frame?.url || url}</div>
        <div ref={browserRef} tabIndex={0} onClick={browserClick} onKeyDown={browserKeyDown} onWheel={(e)=>{const bounds=browserRef.current?.getBoundingClientRect();if(bounds){const scale=Math.min(bounds.width/1280,bounds.height/720);send('wheel',{delta_x:e.deltaX/scale,delta_y:e.deltaY/scale})}}} style={{flex:1,background:'#111827',display:'flex',alignItems:'flex-start',justifyContent:'center',outline:'none',overflow:'hidden',cursor:'default'}}>
          {frame?.image ? <img draggable={false} src={`data:image/jpeg;base64,${frame.image}`} alt="远程浏览器实时画面" style={{width:'100%',height:'100%',objectFit:'contain',objectPosition:'top',userSelect:'none'}}/> : <div style={{color:'#cbd5e1'}}>启动浏览器后将在这里显示实际页面</div>}
        </div>
        {frame?.tabs && frame.tabs.length>1 && <div style={{display:'flex',gap:4,padding:6}}>{frame.tabs.map((item)=><button key={item.index} onClick={()=>send('tab',{index:item.index})} style={{opacity:item.active?1:.65}}>{item.title||item.url}</button>)}</div>}
      </section>
      <section style={{display:'flex',flexDirection:'column',minHeight:0,gap:8}}>
        <div style={{display:'flex',gap:8,alignItems:'center'}}><strong>执行步骤 ({steps.length})</strong><div style={{flex:1}}/><select aria-label="添加断言" defaultValue="" onChange={(e)=>{if(e.target.value)addAssertion(e.target.value as StepAction);e.target.value=''}}><option value="">+ 添加断言</option><option value="assert_visible">元素可见</option><option value="assert_text">包含文本</option><option value="assert_url">URL 匹配</option><option value="assert_title">标题匹配</option><option value="assert_count">元素数量</option></select></div>
        <div style={{overflowY:'auto',minHeight:130,maxHeight:'45%',display:'flex',flexDirection:'column',gap:6}}>{steps.map((step,index)=><div key={step.id} style={{display:'grid',gridTemplateColumns:'90px minmax(60px,1fr) minmax(60px,1fr) minmax(60px,1fr) auto auto',gap:5,alignItems:'center',padding:6,border:'1px solid var(--border-color)',borderRadius:6}}>
          <select aria-label="步骤类型" value={step.action} onChange={(e)=>updateStep(index,{action:e.target.value as StepAction})}>{actions.map((action)=><option key={action} value={action}>{labels[action]}</option>)}</select>
          <input aria-label="步骤说明" value={step.description} onChange={(e)=>updateStep(index,{description:e.target.value})} />{actionInputs(step,index)}
          <button title="从内置浏览器拾取此步骤定位器" disabled={!sessionId} onClick={()=>{pickTargetStepRef.current=step.id;setPickTargetStep(step.id);send('pick_element')}}><Crosshair size={14}/>{pickTargetStep===step.id?'请在页面点击':'拾取'}</button><div style={{display:'flex'}}><button title="上移" disabled={index===0} onClick={()=>{const next=[...steps];[next[index-1],next[index]]=[next[index],next[index-1]];setSteps(next);send('reorder',{ids:next.map(s=>s.id)})}}><ArrowUp size={14}/></button><button title="下移" disabled={index===steps.length-1} onClick={()=>{const next=[...steps];[next[index+1],next[index]]=[next[index],next[index+1]];setSteps(next);send('reorder',{ids:next.map(s=>s.id)})}}><ArrowDown size={14}/></button><button title="删除" onClick={()=>{setSteps(steps.filter((_,i)=>i!==index));send('delete_step',{id:step.id})}}><Trash2 size={14}/></button></div>
        </div>)}</div>
        <details><summary style={{cursor:'pointer'}}>用例和文件设置</summary><div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:6,padding:6}}><input aria-label="Case 名称" value={caseName} onChange={(e)=>setCaseName(e.target.value)}/><input aria-label="测试函数名" value={testName} onChange={(e)=>setTestName(e.target.value)}/><input aria-label="项目文件路径" value={filePath} onChange={(e)=>setFilePath(e.target.value)}/><select value={priority} onChange={(e)=>setPriority(e.target.value as TestCasePriority)}><option value="P1">高优先级</option><option value="P2">中优先级</option><option value="P3">低优先级</option></select><input aria-label="Test Suite / Module" value={suiteName} onChange={(e)=>setSuiteName(e.target.value)} placeholder="Test Suite / Module"/><input aria-label="Case tags" value={tagsText} onChange={(e)=>setTagsText(e.target.value)} placeholder="标签，逗号分隔"/><input aria-label="Pytest markers" value={markersText} onChange={(e)=>setMarkersText(e.target.value)} placeholder="pytest marker，逗号分隔"/></div></details>
        <div style={{flex:1,minHeight:180,border:'1px solid var(--border-color)',borderRadius:6,overflow:'hidden',position:'relative'}}><MonacoEditorPane activeTab={tab} loadingFile={false} showDiffView={false} diffResult={blankDiff} editorRef={editorRef} onEditorReady={()=>{setEditorReady(true);setShowCodeFallback(false)}} onChange={(value)=>setCode(value||'')}/>{showCodeFallback && !editorReady && <textarea aria-label="生成的 Python 脚本" value={code} onChange={(event)=>setCode(event.target.value)} spellCheck={false} style={{position:'absolute',inset:0,width:'100%',height:'100%',resize:'none',border:0,padding:12,fontFamily:'var(--font-mono)',fontSize:13,lineHeight:1.5,background:'var(--surface-primary)',color:'var(--text-primary)'}}/>}</div>
      </section>
    </div>
  </div>;
};
