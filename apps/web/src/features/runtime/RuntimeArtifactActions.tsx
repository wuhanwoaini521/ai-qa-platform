import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import type { RuntimeArtifact } from '../../types/runtime';
import {
  artifactFilename,
  artifactPreviewKind,
  safeArtifactUrl,
} from './artifactModel';
export function RuntimeArtifactActions({
  artifact,
  autoPreview = false,
}: {
  artifact: RuntimeArtifact;
  autoPreview?: boolean;
}) {
  const { t } = useTranslation('runtime');
  const [preview, setPreview] = useState<{ url: string; text: string } | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [zoomOpen, setZoomOpen] = useState(false);
  const generation = useRef(0);
  const objectUrl = useRef<string | null>(null);
  const kind = artifactPreviewKind(artifact);
  useEffect(() => {
    generation.current++;
    setPreview(null);
    setOpen(false);
    setZoomOpen(false);
    return () => {
      generation.current++;
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = null;
    };
  }, [artifact.artifact_id]);
  useEffect(() => {
    if (!zoomOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setZoomOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [zoomOpen]);
  const fetchArtifact = useCallback(async (download: boolean) => {
    if (!artifact.artifact_id) return;
    const current = generation.current;
    setError('');
    setLoading(true);
    try {
      const blob = await api.downloadArtifact(artifact.artifact_id);
      if (current !== generation.current) return;
      if (download) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = artifactFilename(artifact.name);
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
      } else {
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        const url = URL.createObjectURL(blob);
        objectUrl.current = url;
        const text = kind === 'text' ? await blob.slice(0, 65536).text() : '';
        if (current !== generation.current) {
          URL.revokeObjectURL(url);
          return;
        }
        setPreview({ url, text });
        setOpen(true);
      }
    } catch (reason) {
      if (current === generation.current) setError(String(reason));
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [artifact.artifact_id, artifact.name, kind]);
  useEffect(() => {
    if (autoPreview && kind === 'image' && (artifact.size_bytes ?? 0) <= 5 * 1024 * 1024) {
      void fetchArtifact(false);
    }
  }, [autoPreview, artifact.size_bytes, fetchArtifact, kind]);
  const external = safeArtifactUrl(artifact.url);
  return (
    <div className="rt-artifact-actions">
      {artifact.artifact_id && (
        <>
          <button
            disabled={loading}
            className="btn btn-secondary btn-sm"
            onClick={() => void fetchArtifact(true)}
          >
            {t('download')}
          </button>
          {kind && kind !== 'trace' && (
            <button
              disabled={loading || (artifact.size_bytes ?? 0) > 5 * 1024 * 1024}
              className="btn btn-secondary btn-sm"
              onClick={() =>
                preview ? setOpen((value) => !value) : void fetchArtifact(false)
              }
            >
              {kind === 'report' ? t('openReport') : t('preview')}
            </button>
          )}
        </>
      )}
      {kind === 'trace' && (
        <>
          <a
            className="btn btn-secondary btn-sm"
            href="https://trace.playwright.dev/"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('openTraceViewer')}
          </a>
          <small className="rt-trace-viewer-hint">{t('traceViewerHint')}</small>
        </>
      )}
      {external && (
        <a
          className="btn btn-secondary btn-sm"
          href={external}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('open')}
        </a>
      )}
      {loading && <small role="status">{t('loadingArtifact')}</small>}
      {error && <p role="alert">{error}</p>}
      {open && preview && (
        <div className="rt-artifact-preview">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setOpen(false)}
          >
            {t('closePreview')}
          </button>
          {kind === 'image' ? (
            <>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setZoomOpen(true)}>{t('zoomPreview')}</button>
              <img src={preview.url} alt={artifact.name} onClick={() => setZoomOpen(true)} />
            </>
          ) : kind === 'report' ? (
            <iframe title={artifact.name} src={preview.url} sandbox="" />
          ) : (
            <pre>
              {preview.text}
              {(artifact.size_bytes ?? 0) > 65536
                ? `\n${t('previewFirst64KiB')}`
                : ''}
            </pre>
          )}
        </div>
      )}
      {zoomOpen && preview && kind === 'image' && (
        <div className="rt-artifact-zoom-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setZoomOpen(false); }}>
          <section role="dialog" aria-modal="true" aria-label={artifact.name}>
            <button type="button" className="btn btn-secondary btn-sm" autoFocus onClick={() => setZoomOpen(false)}>{t('closePreview')}</button>
            <img src={preview.url} alt={artifact.name} />
          </section>
        </div>
      )}
    </div>
  );
}
