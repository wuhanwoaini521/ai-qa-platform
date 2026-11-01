/** Authoring model for API cases: mirrors the server's ApiCaseRequest. */

export type ApiMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS';

export interface ApiHeaderRow {
  id: string;
  name: string;
  value: string;
}

export type ApiAssertionKind = 'status' | 'json_path' | 'body_contains' | 'json_contract';

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
    if (assertion.kind === 'json_contract') {
      try {
        const schema = JSON.parse(assertion.expected || '');
        if (!schema || typeof schema !== 'object' || typeof schema.type !== 'string') errors.push('errorContractSchema');
      } catch {
        errors.push('errorContractSchema');
      }
    }
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
      if (assertion.kind === 'json_contract') {
        return { kind: 'json_contract', expected: JSON.parse(assertion.expected || '{}') };
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


// ---------------------------------------------------------------------------------------------
// HAR / OpenAPI import (authoring convenience; nothing here executes).

export interface HarDocumentLike {
  log?: {
    entries?: {
      request?: {
        method?: string;
        url?: string;
        headers?: { name?: string; value?: string }[];
        postData?: { text?: string; mimeType?: string };
      };
      response?: { status?: number; content?: { mimeType?: string } };
      _resourceType?: string;
      resourceType?: string;
    }[];
  };
}

export interface OpenApiOperation {
  method: ApiMethod;
  path: string;
  summary: string;
  expectedStatus: string;
  responseSchema?: Record<string, unknown>;
}

// Only the keywords the generated checker understands; anything else is dropped on purpose.
const CONTRACT_KEYS = ['type', 'required', 'properties', 'items'];

function simplifySchema(value: unknown, depth = 0): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || depth > 6) return undefined;
  const source = value as Record<string, unknown>;
  const schema: Record<string, unknown> = {};
  for (const key of CONTRACT_KEYS) {
    if (key === 'properties' && source.properties && typeof source.properties === 'object') {
      schema.properties = Object.fromEntries(
        Object.entries(source.properties as Record<string, unknown>)
          .map(([name, sub]) => [name, simplifySchema(sub, depth + 1)])
          .filter(([, sub]) => sub),
      );
    } else if (key === 'items') {
      const item = simplifySchema(source.items, depth + 1);
      if (item) schema.items = item;
    } else if (key === 'required') {
      if (Array.isArray(source.required)) schema.required = source.required.filter((item) => typeof item === 'string');
    } else if (typeof source[key] === 'string') {
      schema[key] = source[key];
    }
  }
  return typeof schema.type === 'string' ? schema : undefined;
}

const IMPORT_LIMIT = 300;
const MAX_IMPORTED = 300;

/** Turn a HAR file into the same call list the recorder produces. */
export function fromHarDocument(raw: unknown): RecorderApiCall[] {
  if (!raw || typeof raw !== 'object') throw new Error('invalid-har');
  const entries = (raw as HarDocumentLike).log?.entries;
  if (!Array.isArray(entries)) throw new Error('invalid-har');
  const calls: RecorderApiCall[] = [];
  const seen = new Set<string>();
  for (const entry of entries.slice(0, 500)) {
    const request = entry?.request;
    const url = request?.url ?? '';
    const method = (request?.method ?? 'GET').toUpperCase();
    if (!/^https?:/i.test(url)) continue;
    const resourceType = entry?._resourceType ?? entry?.resourceType ?? '';
    const mime = entry?.response?.content?.mimeType ?? '';
    const looksApi = ['xhr', 'fetch'].includes(String(resourceType).toLowerCase()) || /json|graphql/i.test(mime);
    if (!looksApi) continue;
    const status = entry?.response?.status ?? null;
    const key = `${method} ${url} ${status}`;
    if (seen.has(key)) continue;
    seen.add(key);
    calls.push({
      id: `har-${seen.size}`,
      method,
      url,
      status,
      failed: status !== null && status >= 400,
      request_headers: Object.fromEntries(
        (request?.headers ?? [])
          .filter((header) => header?.name)
          .map((header) => [String(header.name).toLowerCase(), String(header.value ?? '')]),
      ),
      request_body: request?.postData?.text ?? null,
      response_content_type: mime,
    });
    if (calls.length >= MAX_IMPORTED) break;
  }
  return calls;
}

/** List HTTP operations from an OpenAPI 3 / Swagger 2 document. */
export function fromOpenApiDocument(raw: unknown): OpenApiOperation[] {
  const document = raw as {
    paths?: Record<string, Record<string, { summary?: string; operationId?: string; responses?: Record<string, unknown> }>>;
  };
  if (!document || typeof document !== 'object' || typeof document.paths !== 'object' || document.paths === null) {
    throw new Error('invalid-openapi');
  }
  const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options']);
  const operations: OpenApiOperation[] = [];
  for (const [path, item] of Object.entries(document.paths).slice(0, IMPORT_LIMIT)) {
    for (const [method, operation] of Object.entries(item ?? {})) {
      if (!methods.has(method.toLowerCase())) continue;
      const responses = (operation?.responses ?? {}) as Record<string, { content?: Record<string, { schema?: unknown }> }>;
      const statuses = Object.keys(responses);
      const preferred = statuses.find((code) => /^2\d\d$/.test(code)) ?? statuses[0] ?? '200';
      const media = responses[preferred]?.content ?? {};
      const jsonSchema = media['application/json']?.schema ?? media['*/*']?.schema;
      operations.push({
        method: method.toUpperCase() as ApiMethod,
        path,
        summary: operation?.summary || operation?.operationId || `${method.toUpperCase()} ${path}`,
        expectedStatus: preferred.replace(/[^0-9]/g, '').slice(0, 3) || '200',
        responseSchema: simplifySchema(jsonSchema),
      });
    }
  }
  return operations.slice(0, IMPORT_LIMIT);
}


// ---------------------------------------------------------------------------------------------
// cURL import and {{variable}} substitution.
// Semantics follow Bruno's documented cURL import (method, headers, body flags, -u, -G, -I, --json,
// scheme-less URLs, -XPOST, ANSI-C strings) while ignoring connection-only flags (-L, -k, -o, proxy,
// timeouts) exactly as Bruno does. See docs/API_RECORDING_DESIGN.md for the reference links.

function decodeAnsiC(value: string): string {
  return value.replace(/\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|.)/g, (match, code: string) => {
    if (code.startsWith('x')) return String.fromCharCode(parseInt(code.slice(1), 16));
    if (code.startsWith('u')) return String.fromCharCode(parseInt(code.slice(1), 16));
    const simple: Record<string, string> = { n: '\n', t: '\t', r: '\r', '\\': '\\', "'": "'", '"': '"' };
    return simple[code] ?? match;
  });
}

function tokenizeCurl(command: string): string[] {
  const tokens: string[] = [];
  let current = '';
  let quote: string | null = null;
  let started = false;
  let ansi = false;
  for (let index = 0; index < command.length; index += 1) {
    const char = command[index];
    if (ansi) {
      if (char === "'") ansi = false;
      else current += char;
      continue;
    }
    if (char === '$' && command[index + 1] === "'") {
      ansi = true;
      started = true;
      index += 1;
      continue;
    }
    if (quote === "'") {
      if (char === "'") quote = null;
      else current += char;
      continue;
    }
    if (quote === '"') {
      if (char === '"') quote = null;
      else if (char === '\\' && index + 1 < command.length) current += command[(index += 1)];
      else current += char;
      continue;
    }
    if (char === '\\' && command[index + 1] === '\n') {
      index += 1;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      started = true;
      continue;
    }
    if (/\s/.test(char)) {
      if (started) {
        tokens.push(current);
        current = '';
        started = false;
      }
      continue;
    }
    current += char;
    started = true;
  }
  if (started) tokens.push(decodeAnsiC(current));
  return tokens;
}

export interface CurlParseResult {
  draft: ApiCaseDraft;
  warnings: string[];
}

const CURL_IGNORED_FLAGS = new Set([
  '-L', '--location', '-k', '--insecure', '-o', '--output', '-O', '--remote-name',
  '-x', '--proxy', '--max-time', '--connect-timeout', '--retry', '-v', '--verbose', '--compressed',
  '--cert', '--key', '--cacert', '-s', '--silent', '-i', '--include',
]);

export function parseCurl(command: string): CurlParseResult {
  const warnings: string[] = [];
  const tokens = tokenizeCurl(command.trim().replace(/^\$\s+/, ''));
  if (tokens[0] === 'curl.exe') tokens[0] = 'curl';
  if (tokens[0] !== 'curl') throw new Error('not-curl');
  const draft = emptyDraft('api_case');
  let url = '';
  const headers: ApiHeaderRow[] = [];
  let method = '';
  let headMode = false;
  let getMode = false;
  let data: string | null = null;
  let jsonMode = false;
  let basicAuth: string | null = null;

  for (let index = 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    const next = () => {
      index += 1;
      return tokens[index] ?? '';
    };
    let flag = token;
    let inlineValue: string | null = null;
    const eq = token.indexOf('=');
    if (token.startsWith('--') && eq > 0) {
      flag = token.slice(0, eq);
      inlineValue = token.slice(eq + 1);
    } else if (/^-[A-Za-z].+/.test(token) && token.length > 2) {
      flag = token.slice(0, 2);
      inlineValue = token.slice(2);
    }
    const value = () => (inlineValue !== null ? inlineValue : next());
    if (CURL_IGNORED_FLAGS.has(flag)) {
      warnings.push(`ignored ${flag}`);
      if (['-o', '--output', '-x', '--proxy', '--max-time', '--connect-timeout', '--retry', '--cert', '--key', '--cacert'].includes(flag)) {
        index += 1;
      }
      continue;
    }
    switch (flag) {
      case '-X':
      case '--request':
        method = value().toUpperCase();
        break;
      case '-H':
      case '--header': {
        const raw = value();
        const colon = raw.indexOf(':');
        if (colon > 0) headers.push(newHeader(raw.slice(0, colon).trim(), raw.slice(colon + 1).trim()));
        break;
      }
      case '-A':
      case '--user-agent':
        headers.push(newHeader('user-agent', value()));
        break;
      case '-d':
      case '--data':
      case '--data-raw':
      case '--data-ascii':
      case '--data-urlencode':
        data = data === null ? value() : `${data}&${value()}`;
        break;
      case '--data-binary': {
        const raw = value();
        data = raw.startsWith('@') ? raw.slice(1) : raw;
        break;
      }
      case '--json':
        jsonMode = true;
        data = value();
        headers.push(newHeader('content-type', 'application/json'));
        break;
      case '-u':
      case '--user': {
        const raw = value();
        basicAuth = raw;
        headers.push(newHeader('authorization', `Basic ${btoa(raw)}`));
        break;
      }
      case '-b':
      case '--cookie':
        headers.push(newHeader('cookie', value()));
        break;
      case '-G':
      case '--get':
        getMode = true;
        break;
      case '-I':
      case '--head':
        headMode = true;
        break;
      default:
        if (flag.startsWith('-')) warnings.push(`unsupported ${flag}`);
        else if (!url) url = token;
        break;
    }
  }

  if (!url) throw new Error('missing-url');
  if (!/^https?:\/\//i.test(url) && !url.startsWith('{{')) url = `https://${url}`;
  if (getMode && data !== null) {
    url += `${url.includes('?') ? '&' : '?'}${data}`;
    data = null;
  }
  if (headMode) method = 'HEAD';
  if (jsonMode && (!method || method === 'GET' || method === 'HEAD')) method = 'POST';
  if (!method) method = data !== null ? 'POST' : 'GET';

  const contentType = headers.find((header) => header.name.toLowerCase() === 'content-type')?.value ?? '';
  const useJson = data !== null && (jsonMode || contentType.includes('json'));
  if (data !== null && useJson) {
    try {
      JSON.parse(data);
    } catch {
      warnings.push('body is not valid JSON');
    }
  }
  if (basicAuth) warnings.push('basic auth is stored as QA_API_SECRET_AUTHORIZATION');

  return {
    draft: {
      ...draft,
      test_name: slugTestName(`${method}_${url.replace(/^https?:\/\/[^/]+/, '')}`),
      method: method as ApiMethod,
      url,
      headers: headers.length ? headers : draft.headers,
      body: data ?? '',
      useJsonBody: useJson,
      assertions: [{ ...newAssertion('status'), expected: '200' }],
    },
    warnings,
  };
}

export interface EnvVariable {
  id: string;
  name: string;
  value: string;
}

export function newVariable(name = '', value = ''): EnvVariable {
  return { id: nextId('v'), name, value };
}

/** Bruno/Postman-style {{name}} substitution, applied before the case is compiled. */
export function substituteVariables(
  text: string,
  variables: EnvVariable[],
): { text: string; unresolved: string[] } {
  const unresolved: string[] = [];
  const byName = new Map(variables.filter((item) => item.name.trim()).map((item) => [item.name.trim(), item.value]));
  const result = text.replace(/\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}/g, (match, name: string) => {
    if (!byName.has(name)) {
      unresolved.push(name);
      return match;
    }
    return byName.get(name) ?? match;
  });
  return { text: result, unresolved };
}
