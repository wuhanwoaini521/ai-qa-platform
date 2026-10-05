import { useEffect, useRef, useState } from 'react';
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
}: {
  artifact: RuntimeArtifact;
}) {
  const { t } = useTranslation('runtime');
  const [preview, setPreview] = useState<{ url: string; text: string } | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const generation = useRef(0);
  const objectUrl = useRef<string | null>(null);
  const kind = artifactPreviewKind(artifact);
  useEffect(() => {
    generation.current++;
    setPreview(null);
    setOpen(false);
    return () => {
      generation.current++;
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = null;
    };
  }, [artifact.artifact_id]);
  const fetchArtifact = async (download: boolean) => {
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
  };
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
          {kind && (
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
            <img src={preview.url} alt={artifact.name} />
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
    </div>
  );
}
