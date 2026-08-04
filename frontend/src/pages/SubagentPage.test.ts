import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buttonByText,
  filesystemManifest,
  filesystemPermissionsManifest,
  modelManifest,
  mountPrimaryPage,
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
    const { wrapper } = await mountPrimaryPage(api)

    const addButton = wrapper.findAll('button').find((button) => button.text() === 'agents.primary.addReference')
    if (!addButton) throw new Error('add reference button not found')
    await addButton.trigger('click')
    await addButton.trigger('click')
    expect(wrapper.findAll('[data-testid="subagent-reference-card"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-action="remove-subagent-reference"]').every((button) => (
      button.classes().includes('ms-auto')
    ))).toBe(true)

    await wrapper.findAll('[data-action="remove-subagent-reference"]')[0]?.trigger('click')
    expect(wrapper.findAll('[data-testid="subagent-reference-card"]')).toHaveLength(1)
    const card = wrapper.get('[data-testid="subagent-reference-card"]')
    await card.get('[data-testid="subagent-reference"]').setValue(
      '00000000-0000-0000-0000-000000000020',
    )
    await flushPromises()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.createPrimaryAgent).toHaveBeenCalledWith(expect.objectContaining({
      subagents: [{
        subagent_id: '00000000-0000-0000-0000-000000000020',
      }],
    }))
    wrapper.unmount()
  })

  it('renders one select per configurable Subagent capability', async () => {
    const api = service()
    const primaryPage = await mountPrimaryPage(api)
    const { wrapper } = await mountSubagentPage(api)

    expect(wrapper.text()).toContain('agents.subagent.roleName')
    expect(wrapper.findAll('[data-capability] input[type="radio"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-capability] select')).toHaveLength(2)
    expect(primaryPage.wrapper.findAll('[data-testid^="primary-capability-filesystem"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-testid^="subagent-capability-filesystem"]')).toHaveLength(2)

    primaryPage.wrapper.unmount()
    wrapper.unmount()
  })

  it('shows fixed filesystem and output-mode values and the full Subagent capability choices', async () => {
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

    expect(wrapper.findAll('[data-capability]')).toHaveLength(4)
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

    const subagent = wrapper.get('[data-testid="subagent-capability-subagent"]')
    expect(subagent.attributes('disabled')).toBeUndefined()
    expect((subagent.element as HTMLSelectElement).value).toBe('__inherit__')
    expect(subagent.find('option[value="__inherit__"]').exists()).toBe(true)
    expect(subagent.find('option[value="__disabled__"]').exists()).toBe(true)
    expect(subagent.findAll('option')).toHaveLength(3)
    await subagent.setValue('00000000-0000-0000-0000-000000000002')
    expect((subagent.element as HTMLSelectElement).value).toBe('00000000-0000-0000-0000-000000000002')
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
          {
            type: 'subagent',
            mode: 'replace',
            block_id: '00000000-0000-0000-0000-000000000002',
          },
        ]),
      }),
    }))
    await subagent.setValue('__disabled__')
    expect((subagent.element as HTMLSelectElement).value).toBe('__disabled__')

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
        subagents: [],
        automation: {
          hook_workflow: { mode: 'inherit', workflow_id: '' },
          lifecycle_workflow: { mode: 'inherit', workflow_id: '' },
        },
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

  it('adds an entity child to a Subagent and can reference itself', async () => {
    const api = service()
    const id = '00000000-0000-0000-0000-000000000020'
    const { wrapper } = await mountSubagentPage(api, `/agents/subagents?id=${id}`)

    await buttonByText(wrapper, 'agents.primary.addReference').trigger('click')
    const reference = wrapper.get('[data-testid="subagent-reference-card"]')
    await reference.get('[data-testid="subagent-reference"]').setValue(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.updateSubagent).toHaveBeenCalledWith(
      id,
      expect.objectContaining({
        settings: expect.objectContaining({
          subagents: [{ subagent_id: id }],
        }),
      }),
    )
    wrapper.unmount()
  })
})
