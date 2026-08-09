import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buttonByText,
  filesystemManifest,
  filesystemPermissionsManifest,
  modelManifest,
  mountMainAgentPage,
  mountSubagentPage,
  outputModeManifest,
  promptManifest,
  resetAgentPageTestState,
  service,
  subagentManifest,
} from './agentPages.testSupport'

beforeEach(resetAgentPageTestState)

describe('Subagent authoring page', () => {
  it('adds, selects, and removes ordered Subagent entity references', async () => {
    const api = service()
    const { wrapper } = await mountMainAgentPage(api)

    const addButton = wrapper.get('[data-action="add-subagent-reference"]')
    await addButton.trigger('click')
    await addButton.trigger('click')
    expect(wrapper.findAll('[data-testid="subagent-reference-row"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-action="remove-subagent-reference"]').every((button) => (
      button.classes().includes('ms-auto')
    ))).toBe(true)

    await wrapper.findAll('[data-action="remove-subagent-reference"]')[0]?.trigger('click')
    expect(wrapper.findAll('[data-testid="subagent-reference-row"]')).toHaveLength(1)
    const row = wrapper.get('[data-testid="subagent-reference-row"]')
    await row.get('[data-testid="subagent-reference"]').setValue(
      '00000000-0000-0000-0000-000000000020',
    )
    await flushPromises()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.createMainAgent).toHaveBeenCalledWith(expect.objectContaining({
      subagents: [{
        subagent_id: '00000000-0000-0000-0000-000000000020',
      }],
    }))
    wrapper.unmount()
  })

  it('renders one select per configurable Subagent capability', async () => {
    const api = service()
    const mainAgentPage = await mountMainAgentPage(api)
    const { wrapper } = await mountSubagentPage(api)

    expect(wrapper.text()).toContain('agents.subagent.roleName')
    expect(wrapper.findAll('[data-capability] input[type="radio"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-capability] select')).toHaveLength(2)
    expect(mainAgentPage.wrapper.findAll('[data-testid^="main-agent-capability-filesystem"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-testid^="subagent-capability-filesystem"]')).toHaveLength(2)

    mainAgentPage.wrapper.unmount()
    wrapper.unmount()
  })

  it('shows fixed inherited values without exposing delegation to Subagents', async () => {
    const api = service({
      getCatalog: vi.fn(async () => ({
        block_types: [
          modelManifest,
          promptManifest,
          filesystemManifest,
          filesystemPermissionsManifest,
          outputModeManifest,
          subagentManifest,
        ],
        editor_defaults: {},
      })),
    })
    const { wrapper } = await mountSubagentPage(api)

    expect(wrapper.findAll('[data-capability]')).toHaveLength(3)
    const filesystem = wrapper.get('[data-testid="subagent-capability-filesystem"]')
    expect(filesystem.attributes('disabled')).toBeDefined()
    expect((filesystem.element as HTMLSelectElement).value).toBe('__inherit__')
    expect(filesystem.text()).toContain('agents.override.mode.inherit')

    const permissions = wrapper.get('[data-testid="subagent-capability-filesystem-permissions"]')
    expect(permissions.attributes('disabled')).toBeUndefined()
    expect((permissions.element as HTMLSelectElement).value).toBe('__inherit__')
    expect(permissions.find('option[value="__disabled__"]').exists()).toBe(true)
    await permissions.setValue('00000000-0000-0000-0000-000000000002')

    const outputMode = wrapper.get('[data-testid="subagent-capability-output-mode"]')
    expect(outputMode.attributes('disabled')).toBeDefined()
    expect((outputMode.element as HTMLSelectElement).value).toBe('__invalid__')
    expect(outputMode.text()).toContain('agents.override.mode.invalid')

    expect(wrapper.find('[data-testid="subagent-capability-subagent"]').exists()).toBe(false)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(api.createSubagent).toHaveBeenCalledWith(expect.objectContaining({
      settings: expect.objectContaining({
        capability_overrides: expect.arrayContaining([
          {
            type: 'filesystem-permissions',
            mode: 'replace',
            block_id: '00000000-0000-0000-0000-000000000002',
          },
        ]),
      }),
    }))

    wrapper.unmount()
  })

  it('adds inherit to Subagent choices and stores disabled or replacement selections', async () => {
    const api = service()
    const { wrapper } = await mountSubagentPage(api)

    const modelSelect = wrapper.get('[data-testid="subagent-capability-model"]')
    const optionalSelect = wrapper.get('[data-testid="subagent-capability-system-prompt"]')
    expect(modelSelect.find('option[value="__inherit__"]').exists()).toBe(true)
    expect(modelSelect.find('option[value="__disabled__"]').exists()).toBe(false)
    expect(optionalSelect.find('option[value="__inherit__"]').exists()).toBe(true)
    expect(optionalSelect.find('option[value="__disabled__"]').exists()).toBe(true)

    await modelSelect.setValue('00000000-0000-0000-0000-000000000001')
    await optionalSelect.setValue('__disabled__')
    await flushPromises()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.createSubagent).toHaveBeenCalledWith({
      component_name: '',
      name: '',
      description: '',
      settings: {
        capability_overrides: [
          { type: 'model', mode: 'replace', block_id: '00000000-0000-0000-0000-000000000001' },
          { type: 'system-prompt', mode: 'disabled', block_id: '' },
        ],
      },
    })
    wrapper.unmount()
  })

  it('loads a Subagent entity from the configuration-library query UUID', async () => {
    const api = service()
    const id = '00000000-0000-0000-0000-000000000020'
    const { wrapper } = await mountSubagentPage(
      api,
      `/agents/subagents?id=${id}`,
    )

    expect(api.getSubagent).toHaveBeenCalledWith(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(api.updateSubagent).toHaveBeenCalledWith(
      id,
      expect.objectContaining({
        component_name: 'Worker component',
        name: 'worker',
      }),
    )
    wrapper.unmount()
  })
})
