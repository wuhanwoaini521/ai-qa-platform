import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Minus, Plus, Scan, Search, X } from 'lucide-react';
import type { KnowledgeNode, ProjectKnowledge } from './types';
import { KIND_ORDER, layoutGraph, visibleGraph } from './graphModel';
import { useGraphViewport } from './useGraphViewport';
import './lifecycle.css';

export function KnowledgeGraph({
  graph,
  initialNode,
  mode = 'knowledge',
}: {
  graph: ProjectKnowledge;
  initialNode?: string;
  mode?: string;
}) {
  const { t } = useTranslation('lifecycle');
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('');
  const [selected, setSelected] = useState<KnowledgeNode | null>(null);
  const [collapsed, setCollapsed] = useState(new Set<string>());
  const view = useGraphViewport();
  const { scale, setScale, offset, setOffset, viewport } = view;
  const source = useMemo(() => {
    const allowed =
      mode === 'mind'
        ? ['requirement', 'criteria', 'rules', 'risks', 'scenarios']
        : mode === 'scenario'
          ? ['flow', 'scenarios', 'design', 'case']
          : KIND_ORDER;
    const nodes = graph.nodes.filter((node) => allowed.includes(node.kind));
    return { ...graph, nodes };
  }, [graph, mode]);
  const filtered = useMemo(
    () => visibleGraph(source, query, kind, collapsed),
    [source, query, kind, collapsed],
  );
  const layout = useMemo(() => layoutGraph(filtered.nodes), [filtered.nodes]);
  const fit = () => view.fit(layout.width, layout.height);
  useEffect(() => {
    setSelected(
      initialNode
        ? (graph.nodes.find(
            (node) =>
              node.id === initialNode || node.id.endsWith(`:${initialNode}`),
          ) ?? null)
        : null,
    );
  }, [graph, initialNode]);
  useEffect(() => {
    setScale(0.75);
    setOffset({ x: 8, y: 8 });
  }, [mode]);
  const neighbors = new Set(
    graph.edges
      .filter(
        (edge) => edge.source === selected?.id || edge.target === selected?.id,
      )
      .flatMap((edge) => [edge.source, edge.target]),
  );
  return (
    <section className="knowledge-shell" aria-label={t('graph')}>
      <div className="lc-toolbar">
        <label className="lc-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('searchGraph')}
            aria-label={t('searchGraph')}
          />
        </label>
        <select
          aria-label={t('filterKind')}
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="">{t('allKinds')}</option>
          {KIND_ORDER.filter((k) => source.nodes.some((n) => n.kind === k)).map(
            (k) => (
              <option key={k} value={k}>
                {t(`kind.${k}`)}
              </option>
            ),
          )}
        </select>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => setScale((v) => Math.max(0.15, v - 0.15))}
          aria-label={t('zoomOut')}
        >
          <Minus size={14} />
        </button>
        <span>{Math.round(scale * 100)}%</span>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => setScale((v) => Math.min(2, v + 0.15))}
          aria-label={t('zoomIn')}
        >
          <Plus size={14} />
        </button>
        <button className="btn btn-secondary btn-sm" onClick={fit}>
          <Scan size={14} />
          {t('fit')}
        </button>
        <span className="lc-muted">
          {filtered.nodes.length} {t('nodes')} · {filtered.edges.length}{' '}
          {t('relations')}
        </span>
      </div>
      {graph.truncated && <p className="lc-notice">{t('truncated')}</p>}
      {!filtered.nodes.length && (
        <p className="lc-empty">{t('noGraphMatches')}</p>
      )}
      <div
        className="knowledge-viewport"
        ref={viewport}
        tabIndex={0}
        aria-label={t('panHint')}
        {...view.handlers}
      >
        <div
          className="knowledge-canvas"
          style={{
            width: layout.width,
            height: layout.height,
            transform: `translate(${offset.x}px,${offset.y}px) scale(${scale})`,
          }}
        >
          <svg width={layout.width} height={layout.height} aria-hidden="true">
            {filtered.edges.map((edge) => {
              const a = layout.positions.get(edge.source),
                b = layout.positions.get(edge.target);
              if (!a || !b) return null;
              return (
                <path
                  key={`${edge.source}:${edge.target}:${edge.relation}`}
                  d={`M${a.x + 210},${a.y + 43} C${a.x + 230},${a.y + 43} ${b.x - 35},${b.y + 43} ${b.x},${b.y + 43}`}
                  className={
                    neighbors.has(edge.source) && neighbors.has(edge.target)
                      ? 'is-related'
                      : ''
                  }
                />
              );
            })}
          </svg>
          {filtered.nodes.map((node) => {
            const pos = layout.positions.get(node.id)!;
            return (
              <div
                key={node.id}
                style={{ left: pos.x, top: pos.y }}
                className={`knowledge-node kind-${node.kind} ${selected?.id === node.id ? 'selected' : ''} ${neighbors.has(node.id) ? 'related' : ''}`}
              >
                <button
                  className="knowledge-node-select"
                  onClick={() => setSelected(node)}
                  aria-pressed={selected?.id === node.id}
                >
                  <small>
                    {t(`kind.${node.kind}`)} {node.status && `· ${node.status}`}
                  </small>
                  <strong>{node.label}</strong>
                  <span>{node.summary}</span>
                </button>
                {graph.edges.some(
                  (edge) =>
                    edge.source === node.id && edge.relation === 'contains',
                ) && (
                  <button
                    className="knowledge-fold"
                    aria-label={t(
                      collapsed.has(node.id) ? 'expand' : 'collapse',
                    )}
                    onClick={() =>
                      setCollapsed((items) => {
                        const next = new Set(items);
                        if (next.has(node.id)) next.delete(node.id);
                        else next.add(node.id);
                        return next;
                      })
                    }
                  >
                    {collapsed.has(node.id) ? '+' : '−'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <p className="lc-caption">
        {t('panHint')} · {t('sourceRelationships')}
      </p>
      {selected && (
        <aside className="knowledge-inspector" aria-label={t('nodeDetails')}>
          <div className="lc-toolbar">
            <span className="lc-eyebrow">{t(`kind.${selected.kind}`)}</span>
            <strong>{selected.label}</strong>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setSelected(null)}
              aria-label={t('close')}
            >
              <X size={14} />
            </button>
          </div>
          <p>{selected.summary}</p>
          {selected.href && (
            <Link className="btn btn-primary btn-sm" to={selected.href}>
              {t('openEntity')}
            </Link>
          )}
          <div className="lc-chip-list">
            {graph.nodes
              .filter(
                (node) => neighbors.has(node.id) && node.id !== selected.id,
              )
              .map((node) => (
                <button
                  className="lc-chip"
                  key={node.id}
                  onClick={() => setSelected(node)}
                >
                  {node.label}
                </button>
              ))}
          </div>
          <details>
            <summary>{t('sourceDocument')}</summary>
            <pre>{JSON.stringify(selected.metadata, null, 2)}</pre>
          </details>
        </aside>
      )}
    </section>
  );
}
