export class APIError extends Error {
  code: string;
  status: number;
  details: unknown;
  requestId?: string;
  constructor(status: number, payload: unknown, fallback: string) {
    const body = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
    const message = typeof body.message === 'string' ? body.message : typeof body.detail === 'string' ? body.detail : fallback;
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.code = typeof body.code === 'string' ? body.code : `HTTP_${status}`;
    this.details = body.details ?? body.detail ?? {};
    this.requestId = typeof body.request_id === 'string' ? body.request_id : undefined;
  }
}

export async function responseError(response: Response): Promise<APIError> {
  let payload: unknown;
  try { payload = await response.json(); } catch { payload = {}; }
  return new APIError(response.status, payload, response.statusText || `Request failed (${response.status})`);
}
