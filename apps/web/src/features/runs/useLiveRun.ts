import { useEffect, useState } from 'react';
import { api, EventStreamError } from '../../api/client';
import type { TestBrowserSession, TestRun } from '../../types';

/** Shared transport for embedded runs: persisted results + transient frames, with bounded state. */
export function useLiveRun(runId: string | null) {
  const [run,setRun]=useState<TestRun|null>(null);
  const [frames,setFrames]=useState<Record<string,string>>({});
  const [sessions,setSessions]=useState<TestBrowserSession[]>([]);
  const [streamStatus,setStreamStatus]=useState<'idle'|'connecting'|'connected'|'reconnecting'|'failed'>('idle');
  const [error,setError]=useState('');
  useEffect(()=>{
    let disposed=false,terminal=false,fetching=false;let close=()=>{};
    setRun(null);setFrames({});setSessions([]);setError('');setStreamStatus(runId?'connecting':'idle');
    if(!runId)return;
    const sync=async()=>{
      if(disposed||fetching)return;fetching=true;
      try {const value=await api.getTestRun(runId);if(disposed)return;setRun(value);setSessions(previous=>value.browser_sessions?.length?value.browser_sessions:previous);
        if(!['RUNNING','QUEUED'].includes(value.status)){terminal=true;close();setStreamStatus('idle');}}
      catch(reason){if(!disposed)setError(String(reason));}finally{fetching=false;}
    };
    close=api.streamRunEvents(runId,event=>{
      if(disposed)return;
      if(event.type==='CONNECTED'){setStreamStatus('connected');setError('');void sync();}
      if(event.type==='BROWSER_FRAME'&&event.session_id&&event.frame){setFrames(previous=>({...previous,[event.session_id]:`data:${event.mime_type||'image/jpeg'};base64,${event.frame}`}));}
      if(event.type==='BROWSER_SESSION'&&event.session?.browser_session_id){const session=event.session as TestBrowserSession;setSessions(previous=>previous.some(item=>item.browser_session_id===session.browser_session_id)?previous.map(item=>item.browser_session_id===session.browser_session_id?{...item,...session}:item):[...previous,session].slice(-100));}
      if(event.type==='BROWSER_TELEMETRY'){const key=({network:'network_logs',console:'console_logs',step:'recent_steps'} as Record<string,string>)[event.channel];if(key)setSessions(previous=>previous.map(item=>item.browser_session_id===event.session_id?{...item,page_evidence:{...item.page_evidence,[key]:[...((item.page_evidence?.[key] as unknown[])??[]),event.entry].slice(-50)}}:item));}
      if(event.type==='LOG_STREAM')setRun(previous=>previous?{...previous,log_output:((previous.log_output??'')+event.log).slice(-20000)}:previous);
      if(['RUN_FINISHED','RUN_ERROR','RUN_CANCELLED'].includes(event.type)){terminal=true;setStreamStatus('idle');void sync();}
      if(['TEST_FINISHED','RUN_STARTED'].includes(event.type))void sync();
    },reason=>{if(disposed||terminal)return;setStreamStatus(reason instanceof EventStreamError&&!reason.retryable?'failed':'reconnecting');setError(String(reason));void sync();});
    void sync();
    const timer=window.setInterval(()=>{if(!terminal)void sync();},1500);
    return()=>{disposed=true;close();window.clearInterval(timer);};
  },[runId]);
  return {run,frames,sessions,streamStatus,error};
}
