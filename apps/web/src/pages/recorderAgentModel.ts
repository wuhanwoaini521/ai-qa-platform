import type { RecorderStep } from '../types';

const locatorKinds = new Set(['role', 'test_id', 'label', 'placeholder', 'id', 'name', 'css', 'text', 'xpath']);

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;

function httpUrl(value: string): string | null {
  try {
    const candidate = value.trim() || 'about:blank';
    const url = new URL(/^(https?:|about:)/i.test(candidate) ? candidate : `https://${candidate}`);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

function locatorFromAgent(value: unknown): RecorderStep['locator'] {
  const locator = asRecord(value);
  if (!locator || typeof locator.value !== 'string' || typeof locator.kind !== 'string' || !locatorKinds.has(locator.kind)) return null;
  return {
    kind: locator.kind as NonNullable<RecorderStep['locator']>['kind'],
    value: locator.value,
    ...(typeof locator.name === 'string' ? { name: locator.name } : {}),
    exact: typeof locator.exact === 'boolean' ? locator.exact : true,
    ...(typeof locator.nth === 'number' ? { nth: locator.nth } : {}),
  };
}

export interface RecorderAgentScript {
  steps: RecorderStep[];
  actionCount: number;
  jevCount: number;
  assertionCount: number;
}

export function recorderStepsFromAgent(output: unknown, startUrl: string): RecorderAgentScript | null {
  const normalizedStartUrl = httpUrl(startUrl);
  const result = asRecord(output);
  if (!normalizedStartUrl || !result || result.verified !== true || result.kind !== 'ai_jev_browser_agent' || !Array.isArray(result.actions)) return null;

  const makeId = () => crypto.randomUUID().replaceAll('-', '').slice(0, 12);
  const steps: RecorderStep[] = [{ id: makeId(), action: 'navigate', url: normalizedStartUrl, description: `打开起始页面：${normalizedStartUrl}` }];
  let actionCount = 0;
  let jevCount = 0;
  const addAction = (raw: unknown) => {
    const item = asRecord(raw);
    if (!item || !['success', 'partial'].includes(String(item.status))) return;
    const agentAction = String(item.action ?? '');
    if (agentAction === 'inspect') return;

    let action: RecorderStep['action'] | null = null;
    if (agentAction === 'navigate') action = 'navigate';
    else if (agentAction === 'back') action = 'back';
    else if (agentAction === 'scroll') action = 'scroll';
    else if (agentAction === 'wait') action = 'wait';
    else if (agentAction === 'fill') action = 'fill';
    else if (agentAction === 'select') action = 'select';
    else if (agentAction === 'hover') action = 'hover';
    else if (agentAction === 'press_key') action = 'press';
    else if (['click', 'open_product', 'filter', 'choose_variant', 'add_to_cart'].includes(agentAction)) {
      action = ['filter', 'choose_variant'].includes(agentAction) && item.target_tag === 'select' ? 'select' : 'click';
    }
    if (!action) return;

    const locator = locatorFromAgent(item.locator);
    const locatorRequired = !['navigate', 'back', 'scroll', 'wait'].includes(action);
    if (locatorRequired && (!locator || item.locator_verified !== true)) return;

    const target = typeof item.target === 'string' ? item.target : agentAction;
    const provider = String(item.decision_provider ?? 'unknown');
    const value = typeof item.value === 'string' ? item.value : '';
    const step: RecorderStep = {
      id: makeId(),
      action,
      description: `${target}${provider === 'jev' ? ' · Jev 已选择' : provider === 'single-candidate' ? ' · 唯一安全候选' : ''}`,
      ...(locator ? {
        locator,
        locator_decision: {
          provider: provider === 'jev' ? 'Jev' : provider,
          model: typeof item.decision_model === 'string' ? item.decision_model : null,
          confidence: typeof item.decision_confidence === 'number' ? item.decision_confidence : null,
          candidate_count: typeof item.candidate_count === 'number' ? item.candidate_count : 1,
          candidate_id: typeof item.candidate_id === 'string' && item.candidate_id ? item.candidate_id : 'observed-candidate',
          verified: item.locator_verified === true,
        },
      } : {}),
      ...(action === 'navigate' ? { url: httpUrl(String(item.url_after ?? '')) ?? undefined } : {}),
      ...(action === 'fill' || action === 'select' ? { value } : {}),
      ...(action === 'press' ? { key: value } : {}),
      ...(action === 'wait' ? { value: String(Math.min(5000, Math.max(100, Number(item.value) || 700))) } : {}),
      ...(action === 'scroll' ? { value: item.value === 'up' ? 'up' : 'down' } : {}),
    };
    if (action === 'navigate' && !step.url) return;
    if ((action === 'fill' || action === 'select') && !step.value) return;
    if (action === 'press' && !step.key) return;
    steps.push(step);
    actionCount += 1;
    if (provider === 'jev') jevCount += 1;
  };
  for (const action of result.actions) addAction(action);

  const evidence = asRecord(result.goal_evidence) ?? {};
  const addTextAssertion = (value: string, description: string) => {
    if (!value.trim() || steps.some((step) => step.action === 'assert_text' && step.value === value)) return;
    steps.push({ id: makeId(), action: 'assert_text', locator: { kind: 'css', value: 'body', exact: false }, value, description });
  };
  const visibleEvidence = [
    ...(Array.isArray(evidence.visible_text_criteria) ? evidence.visible_text_criteria : []),
    ...(Array.isArray(evidence.completion_evidence) ? evidence.completion_evidence : []),
  ].filter((value): value is string => typeof value === 'string' && value.trim().length > 1);
  for (const value of [...new Set(visibleEvidence)].slice(0, 4)) addTextAssertion(value, `验证已观察到的目标证据：${value}`);

  if (evidence.cart_verified === true) {
    const cartAction = [...result.actions].map(asRecord).reverse().find((item) => item?.cart_verified === true);
    const cart = asRecord(cartAction?.cart_after);
    if (typeof cart?.confirmation_text === 'string' && cart.confirmation_text) {
      addTextAssertion(cart.confirmation_text, `验证购物车确认信息：${cart.confirmation_text}`);
    } else if (cart?.badge_text_visible === true && typeof cart.badge_text === 'string') {
      addTextAssertion(cart.badge_text, `验证页面显示的购物车状态：${cart.badge_text}`);
    }
  }

  const title = typeof result.final_title === 'string' ? result.final_title.trim() : '';
  if (title && !steps.some((step) => step.action === 'assert_text' || step.action === 'assert_title')) {
    const escapedTitle = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    steps.push({ id: makeId(), action: 'assert_title', value: `^${escapedTitle}$`, description: `核对最终页面标题：${title}` });
  }

  return { steps, actionCount, jevCount, assertionCount: steps.filter((step) => step.action.startsWith('assert_')).length };
}
