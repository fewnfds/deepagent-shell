import { describe, expect, it } from 'vitest'

import {
  automationWorkflowFromApi,
  automationWorkflowPayload,
  blankAutomationNode,
  blankAutomationWorkflow,
  type HookWorkflowDraft,
  type LifecycleWorkflowDraft,
} from './automation'

describe('automation workflow adapters', () => {
  it('round-trips ordered event nodes and JSON config without special prompt fields', () => {
    const draft = automationWorkflowFromApi('hook-workflow', {
      id: 'workflow-id',
      name: 'Prepare messages',
      hooks: {
        request_prepare: [{ script_id: 'message-script', config: { slot: 'user' } }],
        subagent_before_invoke: [],
        request_end: [],
      },
    }) as HookWorkflowDraft
    draft.hooks.request_prepare.push({
      ...blankAutomationNode(),
      script_id: 'file-script',
      config_text: '{"path":"/context.txt"}',
    })

    expect(automationWorkflowPayload('hook-workflow', draft)).toEqual({
      name: 'Prepare messages',
      hooks: {
        request_prepare: [
          { script_id: 'message-script', config: { slot: 'user' } },
          { script_id: 'file-script', config: { path: '/context.txt' } },
        ],
        subagent_before_invoke: [],
        request_end: [],
      },
    })
  })

  it('keeps timed workflow interval and rejects non-object node config', () => {
    const draft = blankAutomationWorkflow('lifecycle-workflow') as LifecycleWorkflowDraft
    draft.name = 'Refresh data'
    draft.interval_seconds = 2.5
    draft.nodes.push({
      ...blankAutomationNode(),
      script_id: 'refresh-script',
      config_text: '[]',
    })

    expect(() => automationWorkflowPayload('lifecycle-workflow', draft)).toThrow(
      'Automation node config must be a JSON object.',
    )
  })
})
