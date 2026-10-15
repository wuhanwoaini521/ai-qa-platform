import type { RuntimeArtifact } from '../../types/runtime';
export function artifactPreviewKind(artifact: RuntimeArtifact) {
  if (artifact.type?.toUpperCase().includes('TRACE') || /\.zip$/i.test(artifact.name))
    return 'trace';
  if (
    artifact.content_type?.startsWith('image/') ||
    /\.(png|jpe?g|webp|gif)$/i.test(artifact.name)
  )
    return 'image';
  if (
    artifact.content_type?.includes('html') ||
    /\.html?$/i.test(artifact.name)
  )
    return 'report';
  if (
    artifact.content_type?.startsWith('text/') ||
    /\.(py|json|txt|md|patch|diff|xml|log)$/i.test(artifact.name) ||
    ['GENERATED_TEST', 'PATCH_PROPOSAL'].includes(artifact.type)
  )
    return 'text';
  return null;
}
export function artifactFilename(name: string) {
  return (
    name
      .split(/[\\/]/)
      .at(-1)
      ?.replace(/[<>:"|?*\u0000-\u001f]/g, '_') || 'artifact'
  );
}
export function safeArtifactUrl(value: string | null) {
  try {
    const url = new URL(value ?? '');
    return ['https:', 'http:'].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
