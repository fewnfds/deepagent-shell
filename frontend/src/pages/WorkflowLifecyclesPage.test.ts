import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { managementApi, type WorkflowLifecyclePage, type WorkflowLifecycleSummary } from '@/api'
import { useConfirmation } from '@/composables/useConfirmation'
import { useToasts } from '@/composables/useToasts'
import { en } from '@/locales/en'

import WorkflowLifecyclesPage from './WorkflowLifecyclesPage.vue'

const lifecycle: WorkflowLifecycleSummary = {
  lifecycle_id: 'lifecycle-1',
  lifecycle_status: 'active',
  request_id: 'request-1',
  parent_run_id: 'run-1',
  parent_thread_id: 'thread-1',
  parent_status: 'running',
  workflow_id: 'workflow-1',
  workflow_name: 'Research Workflow',
  created_at: '2026-08-17T00:00:00.000+00:00',
  messages_sha: 'sha',
  message_count: 2,
  task_count: 3,
  active_task_count: 1,
  task_status_counts: { running: 1, succeeded: 2 },
  debug_run_count: 3,
  checkpoint_count: 7,
  store_item_count: 6,
  filesystem_count: 1,
  route_count: 2,
  dynamic_directory_count: 1,
}

afterEach(() => {
  vi.restoreAllMocks()
  useConfirmation().cancel()
  const toasts = useToasts()
  for (const toast of toasts.items.value) toasts.dismiss(toast.id)
})

describe('WorkflowLifecyclesPage', () => {
  it('shows lifecycle summaries and performs explicit cleanup', async () => {
    const page: WorkflowLifecyclePage = {
      items: [
        lifecycle,
        { ...lifecycle, lifecycle_id: 'lifecycle-2', lifecycle_status: 'deleting' },
      ],
      page: 1,
      page_size: 10,
      total: 2,
      total_pages: 1,
    }
    const list = vi.spyOn(managementApi, 'listWorkflowLifecycles').mockResolvedValue(page)
    const remove = vi.spyOn(managementApi, 'deleteWorkflowLifecycle').mockResolvedValue({ ok: true })
    const wrapper = mount(WorkflowLifecyclesPage, {
      global: {
        plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })],
      },
    })
    await flushPromises()

    expect(list).toHaveBeenCalledWith({ page: 1, page_size: 10, query: '' })

    expect(wrapper.text()).toContain(lifecycle.workflow_name)
    expect(wrapper.text()).toContain('Running')
    expect(wrapper.text()).toContain('Deleting')
    expect(wrapper.text()).toContain('1 / 3')
    expect(wrapper.text()).toContain('7')
    await wrapper.findAll('button').find((button) => button.text() === 'Delete')!.trigger('click')
    useConfirmation().accept()
    await flushPromises()

    expect(remove).toHaveBeenCalledWith(lifecycle.lifecycle_id)
    wrapper.unmount()
  })
})
