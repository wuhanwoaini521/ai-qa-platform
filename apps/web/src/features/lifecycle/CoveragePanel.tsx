import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { ProjectKnowledge } from './types';

export function CoveragePanel({graph}: {graph: ProjectKnowledge}) {
  const {t} = useTranslation('lifecycle');
  const [selected, setSelected] = useState('criteria');
  const metric = graph.coverage.find(item => item.key === selected);
  return <div className="lc-coverage"><p className="lc-caption">{t('coverageBasis')}</p><div className="lc-metric-grid">{graph.coverage.map(item => <button key={item.key} className={`lc-metric ${selected===item.key?'selected':''}`} onClick={() => setSelected(item.key)} aria-pressed={selected===item.key}><span>{t(`metric.${item.key}`)}</span><strong>{item.percentage === null ? '—' : `${item.percentage}%`}</strong><small>{item.covered} / {item.total} {t('covered')}</small><span className="lc-meter"><i style={{width:`${item.percentage??0}%`}}/></span></button>)}</div>
    {graph.truncated && <p className="lc-notice">{t('truncated')}</p>}
    <div className="lc-table-scroll"><table className="data-table"><thead><tr><th>{t('coverageObject')}</th><th>{t('designCoverage')}</th><th>{t('automation')}</th><th>{t('execution')}</th><th>{t('latestPass')}</th></tr></thead><tbody>{metric?.items.map(item => <tr key={item.id}><td><strong>{item.label}</strong><p className="lc-muted">{item.summary}</p></td><td>{item.covered?t('covered'):t('gap')}<div className="lc-chip-list">{item.case_ids?.map(id => <Link className="lc-chip" key={id} to={`/projects/${graph.project_id}/test-cases/${id}`}>{graph.nodes.find(n=>n.id===id)?.label??id}</Link>)}</div></td><td>{item.automated_case_ids?.length??(selected==='automation'?Number(item.covered):'—')}</td><td>{item.executed_case_ids?.length??(selected==='execution'?Number(item.covered):'—')}</td><td>{item.run_id?<Link to={`/runs/${item.run_id}`}>{item.covered?t('passed'):t('failed')}</Link>:item.passed_case_ids?.length??'—'}</td></tr>)}</tbody></table></div>
    {!metric?.items.length && <p className="lc-empty">{t('noDenominator')}</p>}
    <details><summary>{t('gaps')} · {graph.gaps.length}</summary><div className="lc-stack">{graph.gaps.map(item => <Link key={`${item.kind}:${item.id}`} to={`/projects/${graph.project_id}/requirements/${item.requirement_id}?tab=coverage&node=${item.label}`} className="lc-gap"><strong>{item.label}</strong><span>{item.summary}</span><small>{t(`gapReason.${item.reason}`)}</small></Link>)}</div></details>
  </div>;
}
