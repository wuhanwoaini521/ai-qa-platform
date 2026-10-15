import { useEffect, useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ArrowRight,
  Minus,
  Plus,
  Scan,
  Search,
  X,
} from "lucide-react";
import type { KnowledgeNode, ProjectKnowledge } from "./types";
import {
  GRAPH_NODE_HEIGHT,
  GRAPH_NODE_WIDTH,
  KIND_ORDER,
  defaultGraphFocus,
  focusedGraph,
  layoutGraph,
  visibleGraph,
} from "./graphModel";
import { useGraphViewport } from "./useGraphViewport";
import "./lifecycle.css";

export function KnowledgeGraph({
  graph,
  initialNode,
  mode = "knowledge",
}: {
  graph: ProjectKnowledge;
  initialNode?: string;
  mode?: string;
}) {
  const { t } = useTranslation("lifecycle");
  const markerId = useId().replace(/:/g, "");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [selection, setSelection] = useState<{
    mode: string;
    id: string | null;
  } | null>(null);
  const [collapsed, setCollapsed] = useState(new Set<string>());
  useEffect(() => {
    setQuery("");
    setKind("");
    setSelection(null);
    setCollapsed(new Set());
  }, [mode, initialNode]);
  const view = useGraphViewport();
  const { scale, offset, viewport, fit, zoom } = view;
  const modeGraph = useMemo(() => {
    const allowed =
      mode === "mind"
        ? ["requirement", "criteria", "rules", "risks", "scenarios"]
        : mode === "scenario"
          ? ["flow", "scenarios", "design", "case"]
          : KIND_ORDER;
    const nodes = graph.nodes.filter((node) => allowed.includes(node.kind));
    const ids = new Set(nodes.map((node) => node.id));
    return {
      ...graph,
      nodes,
      edges: graph.edges.filter(
        (edge) => ids.has(edge.source) && ids.has(edge.target),
      ),
    };
  }, [graph, mode]);
  const defaultNode = defaultGraphFocus(modeGraph, mode, initialNode);
  const selectedId = selection?.mode === mode ? selection.id : defaultNode?.id;
  const selected = modeGraph.nodes.find((node) => node.id === selectedId);
  const searching = Boolean(query.trim() || kind);
  const filtered = useMemo(
    () => visibleGraph(modeGraph, query, kind, collapsed),
    [modeGraph, query, kind, collapsed],
  );
  const displayed = useMemo(
    () =>
      selected && !searching ? focusedGraph(filtered, selected.id) : filtered,
    [filtered, selected, searching],
  );
  const layout = useMemo(
    () =>
      layoutGraph(
        displayed.nodes,
        displayed.edges,
        selected && !searching ? selected.id : undefined,
      ),
    [displayed, selected, searching],
  );
  const relations = selected
    ? modeGraph.edges.filter(
        (edge) => edge.source === selected.id || edge.target === selected.id,
      )
    : [];
  const selectNode = (node: KnowledgeNode) => {
    setSelection({ mode, id: node.id });
    setQuery("");
    setKind("");
    setCollapsed(new Set());
  };
  const showAll = () => {
    setSelection({ mode, id: null });
    setQuery("");
    setKind("");
    setCollapsed(new Set());
  };
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const resize = new ResizeObserver(() => fit(layout.width, layout.height));
    resize.observe(element);
    fit(layout.width, layout.height);
    return () => resize.disconnect();
  }, [layout, fit, viewport]);
  const relationLabel = (relation: string) =>
    t(`relation.${relation}`, { defaultValue: relation });
  return (
    <section className="knowledge-shell" aria-label={t("graph")}>
      <div className="lc-toolbar knowledge-tools">
        <label className="lc-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("searchGraph")}
            aria-label={t("searchGraph")}
          />
        </label>
        <select
          aria-label={t("filterKind")}
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="">{t("allKinds")}</option>
          {KIND_ORDER.filter((k) =>
            modeGraph.nodes.some((n) => n.kind === k),
          ).map((k) => (
            <option key={k} value={k}>
              {t(`kind.${k}`)}
            </option>
          ))}
        </select>
        <div className="knowledge-zoom">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => zoom(Math.max(0.01, scale - 0.15))}
            aria-label={t("zoomOut")}
          >
            <Minus size={14} />
          </button>
          <button
            className="btn btn-secondary btn-sm knowledge-scale"
            onClick={() => zoom(1)}
            aria-label={t("readableZoom")}
          >
            {Math.round(scale * 100)}%
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => zoom(Math.min(2, scale + 0.15))}
            aria-label={t("zoomIn")}
          >
            <Plus size={14} />
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => fit(layout.width, layout.height)}
          >
            <Scan size={14} />
            {t("fit")}
          </button>
        </div>
        <span className="knowledge-count" aria-live="polite">
          {t("graphCount", {
            shown: displayed.nodes.length,
            total: modeGraph.nodes.length,
            edges: displayed.edges.length,
          })}
        </span>
      </div>
      <div className="knowledge-scope">
        <label>
          <span>{t("focusNode")}</span>
          <select
            aria-label={t("focusNode")}
            value={selected?.id ?? ""}
            onChange={(e) => {
              const node = modeGraph.nodes.find(
                (item) => item.id === e.target.value,
              );
              if (node) selectNode(node);
              else showAll();
            }}
          >
            <option value="">{t("allRelationships")}</option>
            {modeGraph.nodes.map((node) => (
              <option key={node.id} value={node.id}>
                {t(`kind.${node.kind}`)} · {node.label} · {node.summary}
              </option>
            ))}
          </select>
        </label>
        <button
          className="btn btn-secondary btn-sm"
          onClick={showAll}
          disabled={!selected && !searching && !collapsed.size}
        >
          {t("allRelationships")}
        </button>
      </div>
      {graph.truncated && <p className="lc-notice">{t("truncated")}</p>}
      {selected && !searching && (
        <aside className="knowledge-inspector" aria-label={t("nodeDetails")}>
          <div className="knowledge-detail-heading">
            <span className="lc-eyebrow">{t(`kind.${selected.kind}`)}</span>
            <strong>{selected.label}</strong>
            <span className="knowledge-summary" title={selected.summary}>
              {selected.summary}
            </span>
            {selected.status && (
              <span className="lc-chip">{selected.status}</span>
            )}
            {selected.href && (
              <Link className="btn btn-primary btn-sm" to={selected.href}>
                {t("openEntity")}
                <ArrowRight size={13} />
              </Link>
            )}
            <button
              className="btn btn-secondary btn-sm"
              onClick={showAll}
              aria-label={t("close")}
            >
              <X size={14} />
            </button>
          </div>
          <details className="knowledge-source">
            <summary>
              {t("sourceDocument")} ·{" "}
              {t("relatedCount", { count: relations.length })}
            </summary>
            <div className="knowledge-relation-list">
              {relations.map((edge) => {
                const incoming = edge.target === selected.id;
                const node = modeGraph.nodes.find(
                  (item) => item.id === (incoming ? edge.source : edge.target),
                );
                return (
                  node && (
                    <button
                      className="lc-chip"
                      key={`${edge.source}:${edge.target}:${edge.relation}`}
                      onClick={() => selectNode(node)}
                    >
                      {incoming ? (
                        <ArrowLeft size={13} />
                      ) : (
                        <ArrowRight size={13} />
                      )}
                      <span>
                        {t(incoming ? "upstream" : "downstream")} ·{" "}
                        {relationLabel(edge.relation)} · {node.label}
                      </span>
                    </button>
                  )
                );
              })}
            </div>
            <pre>{JSON.stringify(selected.metadata, null, 2)}</pre>
          </details>
        </aside>
      )}
      {!displayed.nodes.length && (
        <p className="lc-empty">
          {t("noGraphMatches")}{" "}
          <button className="btn btn-secondary btn-sm" onClick={showAll}>
            {t("clearGraphFilters")}
          </button>
        </p>
      )}
      <div
        className="knowledge-viewport"
        ref={viewport}
        role="region"
        tabIndex={0}
        aria-label={t("panHint")}
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
            <defs>
              <marker
                id={markerId}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <polygon points="0,0 10,5 0,10" />
              </marker>
            </defs>
            {displayed.edges.map((edge) => {
              const a = layout.positions.get(edge.source),
                b = layout.positions.get(edge.target);
              if (!a || !b) return null;
              const forward = b.x > a.x;
              const x1 = a.x + (forward ? GRAPH_NODE_WIDTH : 0),
                x2 = b.x + (forward ? 0 : GRAPH_NODE_WIDTH);
              const y1 = a.y + GRAPH_NODE_HEIGHT / 2,
                y2 = b.y + GRAPH_NODE_HEIGHT / 2;
              const bend = forward ? 36 : -36;
              return (
                <g key={`${edge.source}:${edge.target}:${edge.relation}`}>
                  <path
                    d={`M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`}
                    markerEnd={`url(#${markerId})`}
                    className={selected && !searching ? "is-related" : ""}
                  >
                    <title>{relationLabel(edge.relation)}</title>
                  </path>
                  {selected && !searching && (
                    <text
                      className="knowledge-edge-label"
                      x={(x1 + x2) / 2}
                      y={(y1 + y2) / 2 - 5}
                      textAnchor="middle"
                    >
                      {relationLabel(edge.relation)}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
          {displayed.nodes.map((node) => {
            const pos = layout.positions.get(node.id)!;
            return (
              <div
                key={node.id}
                style={{ left: pos.x, top: pos.y }}
                className={`knowledge-node kind-${node.kind} ${selected?.id === node.id ? "selected" : ""}`}
              >
                <button
                  className="knowledge-node-select"
                  onClick={() => selectNode(node)}
                  aria-pressed={selected?.id === node.id}
                  title={`${node.label} · ${node.summary}`}
                >
                  <small>
                    {t(`kind.${node.kind}`)} {node.status && `· ${node.status}`}
                  </small>
                  <strong>{node.label}</strong>
                  <span>{node.summary}</span>
                </button>
                {!selected &&
                  modeGraph.edges.some(
                    (edge) =>
                      edge.source === node.id && edge.relation === "contains",
                  ) && (
                    <button
                      className="knowledge-fold"
                      aria-label={t(
                        collapsed.has(node.id) ? "expand" : "collapse",
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
                      {collapsed.has(node.id) ? "+" : "−"}
                    </button>
                  )}
              </div>
            );
          })}
        </div>
      </div>
      <p className="lc-caption">
        {t(`graphPurpose.${mode}`, {
          defaultValue: t("graphPurpose.knowledge"),
        })}{" "}
        ·{" "}
        {searching
          ? t("graphSearchScope")
          : selected
            ? t("focusHint")
            : t("allGraphHint")}{" "}
        · {t("panHint")} · {t("sourceRelationships")}
      </p>
    </section>
  );
}
