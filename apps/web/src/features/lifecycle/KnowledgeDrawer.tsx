import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { useKnowledge } from './useKnowledge';
import { KnowledgeGraph } from './KnowledgeGraph';

export function KnowledgeDrawer({projectId, entityId, onClose}: {projectId:string;entityId:string;onClose:()=>void}) {
  const {t}=useTranslation('lifecycle'); const knowledge=useKnowledge(projectId,undefined,entityId); const panel=useRef<HTMLDivElement>(null);
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;panel.current?.focus();return()=>previous?.focus();},[]);
  return <div className="lc-drawer-backdrop" onClick={e=>{if(e.target===e.currentTarget)onClose();}}><div className="lc-drawer" ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={t('relatedKnowledge')} onKeyDown={e=>{if(e.key==='Escape')onClose();if(e.key==='Tab'){const controls=panel.current?.querySelectorAll<HTMLElement>('button,a,input,select,[tabindex="0"]');if(!controls?.length)return;const first=controls[0],last=controls[controls.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}}><div className="lc-header"><div><span className="lc-eyebrow">{t('contextKept')}</span><h2>{t('relatedKnowledge')}</h2><p className="lc-muted">{t('whyCase')}</p></div><button className="btn btn-secondary" onClick={onClose} aria-label={t('close')}><X size={18}/></button></div>{knowledge.error&&<p className="lc-notice lc-error">{knowledge.error}</p>}{knowledge.loading&&<p>{t('loading')}</p>}{knowledge.graph&&<KnowledgeGraph graph={knowledge.graph} initialNode={entityId}/>}</div></div>;
}
