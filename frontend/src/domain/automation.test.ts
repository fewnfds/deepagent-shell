import { describe, expect, it } from 'vitest'

import {
  automationPayload,
  blankAutomationPluginBinding,
  normalizeAutomation,
  normalizeSubagentAutomation,
  subagentAutomationPayload,
} from './automation'

describe('automation binding adapters', () => {
  it('round-trips ordered plugin bindings and JSON object config', () => {
    const draft = normalizeAutomation({
      plugins: [{
        plugin_id: 'message-plugin',
        enabled: true,
        config: { slot: 'user' },
      }],
      lifecycle_interval_seconds: 2.5,
    })
    draft.plugins.push({
      ...blankAutomationPluginBinding(),
      plugin_id: 'file-plugin',
      enabled: false,
      config_text: '{"path":"/context.txt"}',
    })

    expect(automationPayload(draft)).toEqual({
      plugins: [
        { plugin_id: 'message-plugin', enabled: true, config: { slot: 'user' } },
        { plugin_id: 'file-plugin', enabled: false, config: { path: '/context.txt' } },
      ],
      lifecycle_interval_seconds: 2.5,
    })
  })

  it('requires object config and clears configuration outside replace mode', () => {
    const draft = normalizeSubagentAutomation({
      mode: 'replace',
      plugins: [{ plugin_id: 'refresh-plugin', config: {} }],
      lifecycle_interval_seconds: 5,
    })
    draft.plugins[0]!.config_text = '[]'
    expect(() => subagentAutomationPayload(draft)).toThrow(
      'Plugin config must be a JSON object.',
    )

    draft.mode = 'disabled'
    expect(subagentAutomationPayload(draft)).toEqual({
      mode: 'disabled',
      plugins: [],
      lifecycle_interval_seconds: null,
    })
  })
})
