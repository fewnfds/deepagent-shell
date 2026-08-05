import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import type { AutomationScriptResource } from '@/api'
import { normalizeAutomation } from '@/domain/automation'
import AutomationPluginBindings from './AutomationPluginBindings.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

const plugin: AutomationScriptResource = {
  api_version: 3,
  id: 'message-injection',
  name: 'Message injection',
  description: '',
  entrypoints: ['prepare'],
  config_schema: {
    type: 'object',
    properties: {
      transform_source: {
        type: 'string',
        title: 'Transform',
        description: '',
        default: '',
        format: 'python',
      },
    },
    required: [],
    additionalProperties: false,
  },
  folder: 'message-injection',
  python_requirements: [],
  requirements_fingerprint: '',
  dependency_status: 'ready',
  dependency_error_code: '',
}

describe('AutomationPluginBindings', () => {
  it('replaces stale config with the selected plugin defaults', async () => {
    const wrapper = mount(AutomationPluginBindings, {
      props: {
        modelValue: normalizeAutomation({
          hooks: [{ plugin_id: '', enabled: true, config: { stale: true } }],
          periodic: [],
        }),
        plugins: [plugin],
        pathPrefix: 'primary-automation',
      },
    })

    await wrapper.get('[data-testid="automation-hooks-plugin"]').setValue(plugin.id)

    const updated = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as ReturnType<
      typeof normalizeAutomation
    >
    expect(updated.hooks[0]?.plugin_id).toBe(plugin.id)
    expect(updated.hooks[0]?.config).toEqual({ transform_source: '' })
  })
})
