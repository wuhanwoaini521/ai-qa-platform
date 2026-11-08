import React, { useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { buildScenarioFlow, edgePath, FlowLayout, FlowNode, ScenarioLike, CriterionLike } from './flowGraph';

interface FlowCanvasProps {
  scenario: ScenarioLike;
  criteria: CriterionLike[];
  sutBaseUrl?: string | null;
  planned?: boolean;
}

const KIND_LABEL: Record<FlowNode['kind'], string> = {
  criterion: 'kindCriterion',
  scenario: 'kindScenario',
  action: 'kindAction',
  assert: 'kindAssert',
};

export const FlowCanvas: React.FC<FlowCanvasProps> = ({ scenario, criteria, sutBaseUrl, planned = false }) => {
  const { t } = useTranslation('flowCanvas');
  const layout: FlowLayout = buildScenarioFlow(scenario, criteria);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1);

  // Fit the widest part of the graph into the viewport instead of clipping the last column.
  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const fit = () => {
      const available = viewport.clientWidth - 48;
      const next = available > 0 ? Math.min(1, available / layout.width) : 1;
      setScale(Number(next.toFixed(3)));
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [layout.width]);
  const nodeById = new Map(layout.nodes.map((node) => [node.id, node]));
  const covered = layout.nodes.filter((node) => node.kind === 'criterion').length;
  const outcomes = layout.nodes.filter((node) => node.kind === 'assert').length;

  return (
    <section className="flow-canvas" aria-label={t('canvasLabel')}>
      <header className="flow-canvas-summary">
        <span className="flow-canvas-chip">{t('chipCriteria', { count: covered })}</span>
        <span className="flow-canvas-chip">{t('chipActions', { count: scenario.actions.length })}</span>
        <span className="flow-canvas-chip">{t('chipOutcomes', { count: outcomes })}</span>
        {sutBaseUrl && <span className="flow-canvas-chip is-muted">{sutBaseUrl}</span>}
        <span className="flow-canvas-hint">{t(planned ? 'planCanvasHint' : 'readOnlyHint')}</span>
      </header>
      <div ref={viewportRef} className="flow-canvas-viewport" tabIndex={0} role="region" aria-label={t('canvasScrollHint')}>
        <div
          className="flow-canvas-surface"
          style={{ width: layout.width * scale, height: layout.height * scale }}
        >
          <div style={{ width: layout.width, height: layout.height, transform: `scale(${scale})`, transformOrigin: 'top left' }}>
          <svg className="flow-canvas-edges" width={layout.width} height={layout.height} aria-hidden="true">
            <defs>
              <marker id="flow-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
                <path d="M0,0 L8,4 L0,8 z" className="flow-canvas-arrow" />
              </marker>
            </defs>
            {layout.edges.map((edge) => {
              const from = nodeById.get(edge.from);
              const to = nodeById.get(edge.to);
              if (!from || !to) return null;
              return (
                <path
                  key={edge.id}
                  d={edgePath(from, to)}
                  className={`flow-canvas-edge is-${edge.kind}`}
                  markerEnd="url(#flow-arrow)"
                />
              );
            })}
          </svg>
          {layout.nodes.map((node) => (
            <article
              key={node.id}
              className={`flow-canvas-node is-${node.kind}`}
              style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
              title={node.subtitle || node.title}
            >
              <span className="flow-canvas-kind">{t(KIND_LABEL[node.kind])}</span>
              {node.index !== undefined && <span className="flow-canvas-index">{node.index}</span>}
              <strong className="flow-canvas-title">{node.title}</strong>
              {node.subtitle && <small className="flow-canvas-subtitle">{node.subtitle}</small>}
            </article>
          ))}
          </div>
        </div>
      </div>
    </section>
  );
};
