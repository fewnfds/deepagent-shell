import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type {
  AgentSessionSummary,
  AgentSessionTimeline,
  ManagementEvent,
  PaginationResponse,
} from '@/api'
import { useConfirmation } from '@/composables/useConfirmation'
import { useToasts } from '@/composables/useToasts'
import { en } from '@/locales/en'

import AgentSessionsPage, { type AgentSessionsApi } from './AgentSessionsPage.vue'

const triggerBrowserDownload = vi.hoisted(() => vi.fn())
vi.mock('@/utils/download', () => ({ triggerBrowserDownload }))

const summary: AgentSessionSummary = {
  session_id: 'session-1',
  model: 'model-1',
  agent_name: 'Primary',
  started_at: '2026-01-02T03:04:00Z',
  updated_at: '2026-01-02T03:04:05Z',
  status: 'completed',
  error_code: null,
  model_call_count: 2,
}

function sessionTimeline(responseSummary = 'final response'): AgentSessionTimeline {
  return {
    session_id: 'session-1',
    token_usage: {
      input_tokens: 1234,
      non_reasoning_output_tokens: 45,
      reasoning_output_tokens: 67,
    },
    runs: [{
      id: 'run-1',
      session_id: 'session-1',
      request_id: 'request-1',
      model: 'model-1',
      agent_name: 'Primary',
      started_at: '2026-01-02T03:04:00Z',
      finished_at: '2026-01-02T03:04:05Z',
      status: 'completed',
      error_code: null,
      input_message_count: 1,
      timeline: [{
        step_id: 'event-0',
        sequence: 1,
        kind: 'tool_call',
        timestamp: '2026-01-02T03:04:02Z',
        data: { tool_name: 'lookup', message: 'tool metadata' },
      }],
      response_summary: responseSummary,
    }],
  }
}

function page(items: AgentSessionSummary[]): PaginationResponse<AgentSessionSummary> {
  return { items, page: 1, page_size: 20, total: items.length, total_pages: 1 }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function i18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: {} },
  })
}

function productI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en },
  })
}

function api(overrides: Partial<AgentSessionsApi> = {}): AgentSessionsApi {
  return {
    listAgentSessions: vi.fn().mockResolvedValue(page([summary])),
    getAgentSession: vi.fn().mockResolvedValue({ session_id: 'session-1', runs: [] }),
    getAgentSessionTimeline: vi.fn().mockResolvedValue(sessionTimeline()),
    getAgentSessionStep: vi.fn().mockResolvedValue({
      kind: 'tool_call',
      data: { tool_name: 'lookup', message: 'tool metadata' },
    }),
    deleteAgentSession: vi.fn().mockResolvedValue({ deleted: true }),
    deleteMatchingAgentSessions: vi.fn().mockResolvedValue({ deleted: 1 }),
    getAgentSessionRetention: vi.fn().mockResolvedValue({ retention_limit: 20 }),
    updateAgentSessionRetention: vi.fn().mockResolvedValue({ retention_limit: 20 }),
    watchApiServerEvents: vi.fn().mockReturnValue(vi.fn()),
    ...overrides,
  }
}

afterEach(() => {
  useConfirmation().cancel()
  const toasts = useToasts()
  for (const toast of toasts.items.value) toasts.dismiss(toast.id)
})

describe('AgentSessionsPage', () => {
  it('keeps list and retention failures inline without also creating toasts', async () => {
    const source = api({
      listAgentSessions: vi.fn().mockRejectedValue(new Error('offline')),
      updateAgentSessionRetention: vi.fn().mockRejectedValue(new Error('save failed')),
    })
    const wrapper = mount(AgentSessionsPage, {
      props: { api: source },
      global: { plugins: [i18n()] },
    })
    await flushPromises()

    const retentionForm = wrapper.get('[data-testid="retention-form"]')
    const retentionInputGroup = retentionForm.get('.input-group')
    expect(retentionInputGroup.get('input').attributes('id')).toBe('session-retention')
    expect(retentionInputGroup.get('button').attributes('type')).toBe('submit')

    expect(wrapper.get('[data-testid="data-table-error"]').attributes('role')).toBe('alert')
    await wrapper.get('[data-testid="retention-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="retention-error"]').attributes('role')).toBe('alert')
    expect(useToasts().items.value).toHaveLength(0)
    wrapper.unmount()
  })

  it('applies query, agent, and status filters while suppressing an older response', async () => {
    const oldResponse = deferred<PaginationResponse<AgentSessionSummary>>()
    const newResponse = deferred<PaginationResponse<AgentSessionSummary>>()
    const listAgentSessions = vi.fn()
      .mockReturnValueOnce(oldResponse.promise)
      .mockReturnValueOnce(newResponse.promise)
    const source = api({ listAgentSessions })
    const wrapper = mount(AgentSessionsPage, {
      props: { api: source },
      global: { plugins: [i18n()] },
    })

    await wrapper.get('#agent-sessions-query').setValue('request-2')
    await wrapper.get('#agent-sessions-filter-agent').setValue('Primary')
    await wrapper.get('#agent-sessions-filter-status').setValue('failed')
    await nextTick()
    await wrapper.get('form[role="search"]').trigger('submit')

    const newer = {
      ...summary,
      session_id: 'session-new',
      agent_name: 'New Primary',
      status: 'failed' as const,
    }
    newResponse.resolve(page([newer]))
    await flushPromises()
    oldResponse.resolve(page([{ ...summary, session_id: 'session-old', agent_name: 'Old Primary' }]))
    await flushPromises()

    expect(listAgentSessions).toHaveBeenNthCalledWith(2, {
      page: 1,
      page_size: 20,
      query: 'request-2',
      agent: 'Primary',
      status: 'failed',
    })
    expect(wrapper.text()).toContain('New Primary')
    expect(wrapper.text()).not.toContain('Old Primary')
  })

  it('deletes complete sessions using only the submitted filters', async () => {
    const source = api()
    const wrapper = mount(AgentSessionsPage, {
      props: { api: source },
      global: { plugins: [productI18n()] },
    })
    await flushPromises()

    await wrapper.get('#agent-sessions-query').setValue('session-1')
    const bulk = wrapper.findAll('button').find((button) => (
      button.text() === 'Delete filtered results'
    ))!
    expect(bulk.attributes('disabled')).toBeDefined()
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()
    await bulk.trigger('click')
    useConfirmation().accept()
    await flushPromises()

    expect(source.deleteMatchingAgentSessions).toHaveBeenCalledWith({
      query: 'session-1',
      agent: '',
      status: '',
    })
  })

  it('renders a compact session list and downloads the complete session as JSON', async () => {
    const source = api()
    const wrapper = mount(AgentSessionsPage, {
      props: { api: source },
      global: { plugins: [i18n()] },
    })
    await flushPromises()

    const row = wrapper.get('[data-testid="data-table-row"]')
    expect(wrapper.get('[data-testid="data-table"]').get('table').element.tagName).toBe('TABLE')
    expect(wrapper.find('[data-testid="session-card"]').exists()).toBe(false)
    expect(row.text()).toContain('Primary')
    expect(row.text()).toContain('2')
    expect(row.text()).not.toContain('session-1')
    expect(row.find('.text-bg-success').exists()).toBe(false)

    await row.get('[data-action="download-session"]').trigger('click')
    await flushPromises()

    expect(source.getAgentSession).toHaveBeenCalledWith('session-1')
    expect(triggerBrowserDownload).toHaveBeenCalledWith(
      expect.any(Blob),
      'agent-session-session-1.json',
    )
    wrapper.unmount()
  })

  it('loads details on demand and refreshes matching list/detail after SSE', async () => {
    let eventHandler: ((event: ManagementEvent) => void) | null = null
    const getAgentSessionTimeline = vi.fn()
      .mockResolvedValueOnce(sessionTimeline('first response'))
      .mockResolvedValueOnce(sessionTimeline('updated response'))
    const source = api({
      getAgentSessionTimeline,
      watchApiServerEvents: vi.fn((handler: (event: ManagementEvent) => void) => {
        eventHandler = handler
        return vi.fn()
      }),
    })
    const wrapper = mount(AgentSessionsPage, {
      props: { api: source },
      global: { plugins: [productI18n()] },
      attachTo: document.body,
    })
    await flushPromises()

    expect(getAgentSessionTimeline).not.toHaveBeenCalled()
    await wrapper.get('[data-action="show-session"]').trigger('click')
    await flushPromises()
    expect(getAgentSessionTimeline).toHaveBeenCalledWith('session-1')
    expect(wrapper.get('[data-testid="session-timeline"]').text()).toContain('first response')
    expect(wrapper.get('[data-testid="session-input-tokens"]').text()).toContain('1,234 tokens')
    expect(wrapper.get('[data-testid="session-output-content-tokens"]').text()).toContain('45 tokens')
    expect(wrapper.get('[data-testid="session-output-reasoning-tokens"]').text()).toContain('67 tokens')

    eventHandler?.({ type: 'agent_session_changed', session_id: 'session-1' })
    await flushPromises()
    expect(getAgentSessionTimeline).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="session-timeline"]').text()).toContain('updated response')
    expect(source.listAgentSessions).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('loads each Timeline step JSON only when viewed and keeps complete JSON outside details', async () => {
    const longToolResult = `large result ${'x'.repeat(500)}`
    const detailed = sessionTimeline('final answer')
    detailed.runs[0]!.timeline = [
      {
        step_id: 'event-0',
        sequence: 1,
        timestamp: '2026-01-02T03:04:01Z',
        kind: 'model_request',
        data: {
          model_name: 'provider-model',
          message_count: 1,
          tool_count: 1,
        },
      },
      {
        step_id: 'event-1',
        sequence: 2,
        timestamp: '2026-01-02T03:04:02Z',
        kind: 'tool_call',
        data: { tool_name: 'lookup', arguments: '{"query":"weather"}' },
      },
      {
        step_id: 'event-2',
        sequence: 3,
        timestamp: '2026-01-02T03:04:03Z',
        kind: 'tool_result',
        data: { tool_name: 'lookup', output: 'large result summary' },
      },
      {
        step_id: 'event-3',
        sequence: 4,
        timestamp: '2026-01-02T03:04:04Z',
        kind: 'model_request',
        data: { model_name: 'provider-model', message_count: 0, tool_count: 0 },
      },
      {
        step_id: 'event-4',
        sequence: 5,
        timestamp: '2026-01-02T03:04:04Z',
        kind: 'subagent',
        data: { phase: 'start', subagent_name: 'Researcher' },
      },
    ]
    const getAgentSession = vi.fn().mockResolvedValue({
      session_id: 'session-1',
      runs: [{ response_text: longToolResult }],
    })
    const getAgentSessionStep = vi.fn().mockResolvedValue({
      sequence: 3,
      timestamp: '2026-01-02T03:04:03Z',
      kind: 'tool_result',
      data: { tool_name: 'lookup', output: longToolResult },
    })
    const wrapper = mount(AgentSessionsPage, {
      props: {
        api: api({
          getAgentSession,
          getAgentSessionTimeline: vi.fn().mockResolvedValue(detailed),
          getAgentSessionStep,
        }),
      },
      global: { plugins: [productI18n()] },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-action="show-session"]').trigger('click')
    await flushPromises()

    const timeline = wrapper.get('[data-testid="session-timeline"]')
    expect(timeline.text()).toContain('Model request 1: Primary calls model provider-model')
    expect(timeline.text()).toContain('Model request 1: call tool lookup')
    expect(timeline.text()).toContain('Model request 1: tool lookup completed')
    expect(timeline.text()).toContain('Model request 2: Primary calls model provider-model')
    expect(timeline.text()).toContain('Model request 2: Subagent Researcher started')
    expect(timeline.text()).toContain('Model request 2: Primary returns the final response')
    expect(getAgentSession).not.toHaveBeenCalled()
    expect(getAgentSessionStep).not.toHaveBeenCalled()
    expect(document.body.textContent).not.toContain(longToolResult)

    await wrapper.get('[data-step-id="run-1:event-2"]').trigger('click')
    await flushPromises()

    expect(getAgentSessionStep).toHaveBeenCalledWith('session-1', 'run-1', 'event-2')
    const stepJson = wrapper.get('[data-testid="timeline-step-json"]')
    expect(stepJson.element.tagName).toBe('TEXTAREA')
    expect(stepJson.attributes('readonly')).toBeDefined()
    expect(stepJson.classes()).toContain('session-timeline-json')
    expect((stepJson.element as HTMLTextAreaElement).value).toContain(longToolResult)
    expect((stepJson.element as HTMLTextAreaElement).value).toContain('\n')
    expect(wrapper.find('[data-testid="session-json"]').exists()).toBe(false)

    await wrapper.get('[data-step-id="run-1:event-2"]').trigger('click')
    expect(wrapper.find('[data-testid="timeline-step-json"]').exists()).toBe(false)
    await wrapper.get('[data-step-id="run-1:event-2"]').trigger('click')
    expect(getAgentSessionStep).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('[data-action="close-modal"]')).toHaveLength(1)
    expect(wrapper.find('.modal-footer').exists()).toBe(false)
    wrapper.unmount()
  })

  it('confirms before lowering retention deletes old session runs', async () => {
    const updateAgentSessionRetention = vi.fn().mockResolvedValue({
      retention_limit: 5,
    })
    const source = api({ updateAgentSessionRetention })
    const wrapper = mount(AgentSessionsPage, {
      props: { api: source },
      global: { plugins: [i18n()] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="retention-form"] input').setValue(5)
    await wrapper.get('[data-testid="retention-form"]').trigger('submit')

    expect(useConfirmation().current.value).toMatchObject({
      title: 'agentSessions.retention.confirmTitle',
      dangerous: true,
    })
    expect(updateAgentSessionRetention).not.toHaveBeenCalled()

    useConfirmation().accept()
    await flushPromises()
    expect(updateAgentSessionRetention).toHaveBeenCalledWith(5)
    wrapper.unmount()
  })

  it('deletes by session ID after shared confirmation accepts', async () => {
    const source = api()
    const wrapper = mount(AgentSessionsPage, {
      props: { api: source },
      global: { plugins: [i18n()] },
    })
    await flushPromises()

    void wrapper.get('[data-action="delete-session"]').trigger('click')
    await nextTick()
    useConfirmation().accept()
    await flushPromises()

    expect(source.deleteAgentSession).toHaveBeenCalledWith('session-1')
  })
})
