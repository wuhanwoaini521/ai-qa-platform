export type BrowserFramePresentation = 'live' | 'lastReceived' | 'lastCaptured' | null;

export type BrowserStreamStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';

export function browserFramePresentation({
  hasStreamFrame,
  hasCapturedFrame,
  sessionStatus,
  streamStatus,
}: {
  hasStreamFrame: boolean;
  hasCapturedFrame: boolean;
  sessionStatus?: string | null;
  streamStatus: BrowserStreamStatus;
}): BrowserFramePresentation {
  if (!hasStreamFrame && !hasCapturedFrame) return null;
  if (hasStreamFrame && sessionStatus?.toLowerCase() === 'running' && streamStatus === 'connected') {
    return 'live';
  }
  if (hasStreamFrame) return 'lastReceived';
  return 'lastCaptured';
}
