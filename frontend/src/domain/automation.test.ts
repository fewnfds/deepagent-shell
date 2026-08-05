import { describe, expect, it } from 'vitest'

import {
  automationPayload,
  blankAutomationPluginBinding,
  blankPeriodicAutomationPluginBinding,
  normalizeAutomation,
  normalizeSubagentAutomation,
  subagentAutomationPayload,
} from './automation'

describe('automation binding adapters', () => {
  it('round-trips separate Hook and independently scheduled periodic bindings', () => {
    const draft = normalizeAutomation({
      hooks: [{
        plugin_id: 'message-plugin',
        enabled: true,
        config: { slot: 'user' },
      }],
      periodic: [{
        plugin_id: 'refresh-plugin',
        enabled: true,
        config: { source: 'market' },
        interval_seconds: 2.5,
      }],
    })
    draft.hooks.push({
      ...blankAutomationPluginBinding(),
      plugin_id: 'file-plugin',
      enabled: false,
      config: { path: '/context.txt' },
    })
    draft.periodic.push({
      ...blankPeriodicAutomationPluginBinding(),
      plugin_id: 'slow-refresh-plugin',
      interval_seconds: 30,
    })

    expect(automationPayload(draft)).toEqual({
      hooks: [
        { plugin_id: 'message-plugin', enabled: true, config: { slot: 'user' } },
        { plugin_id: 'file-plugin', enabled: false, config: { path: '/context.txt' } },
      ],
      periodic: [
        {
          plugin_id: 'refresh-plugin',
          enabled: true,
          config: { source: 'market' },
          interval_seconds: 2.5,
        },
        {
          plugin_id: 'slow-refresh-plugin',
          enabled: true,
          config: {},
          interval_seconds: 30,
        },
      ],
    })
  })

  it('keeps Hook and periodic Subagent overrides independent', () => {
    const draft = normalizeSubagentAutomation({
      hooks: {
        mode: 'replace',
        plugins: [{ plugin_id: 'context-plugin', config: {} }],
      },
      periodic: {
        mode: 'disabled',
        plugins: [],
      },
    })
    draft.hooks.plugins[0]!.config = { transform_source: 'return messages' }
    expect(subagentAutomationPayload(draft).hooks.plugins[0]?.config).toEqual({
      transform_source: 'return messages',
    })

    draft.hooks.mode = 'inherit'
    expect(subagentAutomationPayload(draft)).toEqual({
      hooks: { mode: 'inherit', plugins: [] },
      periodic: { mode: 'disabled', plugins: [] },
    })
  })
})
