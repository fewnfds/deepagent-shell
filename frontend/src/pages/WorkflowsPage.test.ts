import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { managementApi, type MainAgent, type Workflow } from '@/api'
import { useConfirmation } from '@/composables/useConfirmation'
import { useToasts } from '@/composables/useToasts'
import { en } from '@/locales/en'

import WorkflowsPage from './WorkflowsPage.vue'

function i18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

const mainAgent = {
  id: 'agent-1',
  name: 'Research Agent',
} as MainAgent

const workflow: Workflow = {
  id: 'workflow-1',
  name: 'Research Workflow',
  description: 'Runs the research agent.',
  main_agent_id: mainAgent.id,
  main_agent_name: mainAgent.name,
  enabled: true,
}

afterEach(() => {
  vi.restoreAllMocks()
  useConfirmation().cancel()
  const toasts = useToasts()
  for (const toast of toasts.items.value) toasts.dismiss(toast.id)
})

describe('WorkflowsPage', () => {
  it('loads Workflows and performs create and delete operations', async () => {
    vi.spyOn(managementApi, 'listMainAgents').mockResolvedValue([mainAgent])
    vi.spyOn(managementApi, 'listWorkflows').mockResolvedValue([workflow])
    const create = vi.spyOn(managementApi, 'createWorkflow').mockResolvedValue(workflow)
    const remove = vi.spyOn(managementApi, 'deleteWorkflow').mockResolvedValue({ ok: true })

    const wrapper = mount(WorkflowsPage, { global: { plugins: [i18n()] } })
    await flushPromises()

    expect(wrapper.text()).toContain(workflow.name)
    await wrapper.findAll('button').find((button) => button.text() === 'New')!.trigger('click')
    await flushPromises()

    await wrapper.get('#workflow-form input[type="text"]').setValue('New Workflow')
    await wrapper.get('#workflow-form textarea').setValue('New description')
    await wrapper.get('#workflow-form select').setValue(mainAgent.id)
    await wrapper.get('#workflow-form').trigger('submit')
    await flushPromises()

    expect(create).toHaveBeenCalledWith({
      name: 'New Workflow',
      description: 'New description',
      main_agent_id: mainAgent.id,
      enabled: true,
    })

    await wrapper.findAll('button').find((button) => button.text() === 'Delete')!.trigger('click')
    useConfirmation().accept()
    await flushPromises()

    expect(remove).toHaveBeenCalledWith(workflow.id)
    wrapper.unmount()
  })
})
