/** Authoring model for API cases: mirrors the server's ApiCaseRequest. */

export type ApiMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS';

export interface ApiHeaderRow {
  id: string;
  name: string;
  value: string;
}

export type ApiAssertionKind = 'status' | 'json_path' | 'body_contains';

export interface ApiAssertion {
  id: string;
  kind: ApiAssertionKind;
  path: string;
  expected: string;
}

export interface ApiCaseDraft {
  test_name: string;
  method: ApiMethod;
  url: string;
  headers: ApiHeaderRow[];
  body: string;
  useJsonBody: boolean;
  assertions: ApiAssertion[];
}

export interface RecorderApiCall {
  id: string;
  method: string;
  url: string;
  status: number | null;
  failed: boolean;
  request_headers: Record<string, string>;
  request_body: string | null;
  response_content_type: string;
}

let counter = 0;
const nextId = (prefix: string) => `${prefix}${Date.now().toString(36)}${(counter += 1)}`;

export function newHeader(name = '', value = ''): ApiHeaderRow {
  return { id: nextId('h'), name, value };
}

export function newAssertion(kind: ApiAssertionKind = 'status'): ApiAssertion {
  return { id: nextId('a'), kind, path: '', expected: kind === 'status' ? '200' : '' };
}

export function emptyDraft(testName = 'api_case'): ApiCaseDraft {
  return {
    test_name: testName,
    method: 'GET',
    url: '',
    headers: [newHeader('accept', 'application/json')],
    body: '',
    useJsonBody: false,
    assertions: [newAssertion('status')],
  };
}

export function slugTestName(title: string, fallback = 'api_case'): string {
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return `test_${slug || fallback}`.slice(0, 60);
}

export function fromRecorderCall(call: RecorderApiCall): ApiCaseDraft {
  const url = call.url;
  const path = url.replace(/^https?:\/\/[^/]+/, '') || '/';
  const headers = Object.entries(call.request_headers ?? {})
    .filter(([name]) => !['host', 'connection', 'content-length'].includes(name.toLowerCase()))
    .map(([name, value]) => newHeader(name, value));
  const draft = emptyDraft(slugTestName(`${call.method}_${path.replace(/[^a-z0-9]+/gi, '_')}`));
  return {
    ...draft,
    method: call.method as ApiMethod,
    url: path,
    headers: headers.length ? headers : draft.headers,
    body: call.request_body ?? '',
    useJsonBody: Boolean(call.request_body?.trim().startsWith('{') || call.request_body?.trim().startsWith('[')),
    assertions: [{ ...newAssertion('status'), expected: String(call.status ?? 200) }],
  };
}

export interface DraftValidation {
  errors: string[];
  warnings: string[];
}

export function validateDraft(draft: ApiCaseDraft): DraftValidation {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!draft.test_name.trim()) errors.push('errorTestName');
  if (!draft.url.trim()) errors.push('errorUrl');
  if (draft.body.trim() && draft.useJsonBody) {
    try {
      JSON.parse(draft.body);
    } catch {
      errors.push('errorJsonBody');
    }
  }
  for (const assertion of draft.assertions) {
    if (assertion.kind === 'json_path' && !assertion.path.trim()) errors.push('errorJsonPath');
    if (assertion.kind === 'status' && !/^\d{3}$/.test(assertion.expected.trim())) errors.push('errorStatus');
  }
  if (!draft.assertions.some((item) => item.kind === 'status')) warnings.push('warnNoStatus');
  return { errors, warnings };
}

export function toPayload(draft: ApiCaseDraft): Record<string, unknown> {
  const headers = draft.headers
    .filter((header) => header.name.trim())
    .map((header) => ({ name: header.name.trim(), value: header.value }));
  const payload: Record<string, unknown> = {
    test_name: draft.test_name.trim(),
    method: draft.method,
    url: draft.url.trim(),
    headers,
    assertions: draft.assertions.map((assertion) => {
      if (assertion.kind === 'status') return { kind: 'status', expected: Number(assertion.expected) || 200 };
      if (assertion.kind === 'json_path') {
        const expected = assertion.expected.trim();
        let parsed: unknown = expected;
        try {
          parsed = JSON.parse(expected);
        } catch {
          /* keep the raw string when it is not valid JSON */
        }
        return { kind: 'json_path', path: assertion.path.trim(), expected: parsed };
      }
      return { kind: 'body_contains', expected: assertion.expected };
    }),
  };
  if (draft.body.trim()) {
    if (draft.useJsonBody) payload.json_body = JSON.parse(draft.body);
    else payload.body = draft.body;
  }
  return payload;
}
