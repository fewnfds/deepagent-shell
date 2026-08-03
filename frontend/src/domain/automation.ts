import type {
  AutomationNode,
  AutomationWorkflowPayload,
  AutomationWorkflowType,
  HookWorkflowPayload,
  LifecycleWorkflowPayload,
  SavedAutomationWorkflow,
} from '@/api'

export interface AutomationNodeDraft {
  key: string
  script_id: string
  config_text: string
}

export interface HookWorkflowDraft {
  id: string
  name: string
  hooks: {
    request_prepare: AutomationNodeDraft[]
    subagent_before_invoke: AutomationNodeDraft[]
    request_end: AutomationNodeDraft[]
  }
}

export interface LifecycleWorkflowDraft {
  id: string
  name: string
  interval_seconds: number
  nodes: AutomationNodeDraft[]
}

export type AutomationWorkflowDraft = HookWorkflowDraft | LifecycleWorkflowDraft
export type HookName = keyof HookWorkflowDraft['hooks']

let nodeSequence = 0

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function nodeDraft(value: unknown = {}): AutomationNodeDraft {
  const source = record(value)
  nodeSequence += 1
  return {
    key: `automation-node-${nodeSequence}`,
    script_id: text(source.script_id),
    config_text: JSON.stringify(record(source.config), null, 2),
  }
}

export function blankAutomationNode(): AutomationNodeDraft {
  return nodeDraft()
}

export function blankAutomationWorkflow(
  type: AutomationWorkflowType,
): AutomationWorkflowDraft {
  if (type === 'hook-workflow') {
    return {
      id: '',
      name: '',
      hooks: {
        request_prepare: [],
        subagent_before_invoke: [],
        request_end: [],
      },
    }
  }
  return { id: '', name: '', interval_seconds: 2, nodes: [] }
}

export function automationWorkflowFromApi(
  type: AutomationWorkflowType,
  value: SavedAutomationWorkflow,
): AutomationWorkflowDraft {
  const source = record(value)
  if (type === 'hook-workflow') {
    const hooks = record(source.hooks)
    const list = (name: HookName): AutomationNodeDraft[] => (
      Array.isArray(hooks[name]) ? hooks[name].map(nodeDraft) : []
    )
    return {
      id: text(source.id),
      name: text(source.name),
      hooks: {
        request_prepare: list('request_prepare'),
        subagent_before_invoke: list('subagent_before_invoke'),
        request_end: list('request_end'),
      },
    }
  }
  return {
    id: text(source.id),
    name: text(source.name),
    interval_seconds: typeof source.interval_seconds === 'number'
      ? source.interval_seconds
      : 2,
    nodes: Array.isArray(source.nodes) ? source.nodes.map(nodeDraft) : [],
  }
}

function nodePayload(value: AutomationNodeDraft): AutomationNode {
  const parsed: unknown = JSON.parse(value.config_text || '{}')
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Automation node config must be a JSON object.')
  }
  return {
    script_id: value.script_id,
    config: parsed as Record<string, unknown>,
  }
}

export function automationWorkflowPayload(
  type: AutomationWorkflowType,
  value: AutomationWorkflowDraft,
): AutomationWorkflowPayload {
  if (type === 'hook-workflow') {
    const draft = value as HookWorkflowDraft
    const payload: HookWorkflowPayload = {
      name: draft.name,
      hooks: {
        request_prepare: draft.hooks.request_prepare.map(nodePayload),
        subagent_before_invoke: draft.hooks.subagent_before_invoke.map(nodePayload),
        request_end: draft.hooks.request_end.map(nodePayload),
      },
    }
    return payload
  }
  const draft = value as LifecycleWorkflowDraft
  const payload: LifecycleWorkflowPayload = {
    name: draft.name,
    interval_seconds: draft.interval_seconds,
    nodes: draft.nodes.map(nodePayload),
  }
  return payload
}

