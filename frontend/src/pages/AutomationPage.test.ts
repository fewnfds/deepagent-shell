import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { managementApi } from '@/api'
import AutomationPage from './AutomationPage.vue'

const toastNotify = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ notify: toastNotify }),
}))

vi.mock('@/composables/useConfirmation', () => ({
  useConfirmation: () => ({ confirm: vi.fn(async () => true) }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

afterEach(() => {
  vi.restoreAllMocks()
  toastNotify.mockReset()
})

describe('AutomationPage', () => {
  it('saves an ordered custom-script event workflow', async () => {
    vi.spyOn(managementApi, 'listAutomationWorkflows').mockResolvedValue([])
    vi.spyOn(managementApi, 'listAutomationScripts').mockResolvedValue({
      catalog: [{
        api_version: 1,
        id: 'message-script',
        name: 'Message script',
        description: 'Updates prepared messages.',
        triggers: ['hook'],
        folder: 'message-script',
      }],
      errors: {},
    })
    const validateDraft = vi.spyOn(managementApi, 'validateDraft').mockResolvedValue({
      valid: true,
      stage: 'workflow_draft',
      issues: [],
    })
    const save = vi.spyOn(managementApi, 'saveAutomationWorkflow').mockResolvedValue({
      id: 'workflow-id',
      name: 'Prepare request',
      hooks: {
        request_prepare: [{ script_id: 'message-script', config: { slot: 'user' } }],
        subagent_before_invoke: [],
        request_end: [],
      },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/automation/:type', component: AutomationPage }],
    })
    await router.push('/automation/hook-workflow')
    await router.isReady()
    const wrapper = mount(AutomationPage, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.get('[data-field="record-name"]').setValue('Prepare request')
    await wrapper.findAll('button[aria-label="automation.nodes.add"]')[0]?.trigger('click')
    const firstNode = wrapper.findAll('.list-group-item')[0]
    if (!firstNode) throw new Error('request preparation node was not added')
    await firstNode.get('select').setValue('message-script')
    await firstNode.get('textarea').setValue('{"slot":"user"}')
    const saveButton = wrapper.findAll('button').find((button) => (
      button.text().includes('common.save')
    ))
    if (!saveButton) throw new Error('save button not found')
    await saveButton.trigger('click')
    await flushPromises()

    expect(validateDraft).toHaveBeenLastCalledWith({
      target: {
        kind: 'automation',
        type: 'hook-workflow',
        id: '',
      },
      payload: {
        name: 'Prepare request',
        hooks: {
          request_prepare: [
            { script_id: 'message-script', config: { slot: 'user' } },
          ],
          subagent_before_invoke: [],
          request_end: [],
        },
      },
    })
    expect(save).toHaveBeenCalledWith('hook-workflow', {
      name: 'Prepare request',
      hooks: {
        request_prepare: [
          { script_id: 'message-script', config: { slot: 'user' } },
        ],
        subagent_before_invoke: [],
        request_end: [],
      },
    })
    expect(toastNotify).toHaveBeenCalledWith({
      tone: 'success',
      title: 'automation.feedback.saved',
    })
    wrapper.unmount()
  })
})
