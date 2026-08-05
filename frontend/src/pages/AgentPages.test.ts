import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ManagementApiError } from '@/api'
import type { PrimaryAgentProfile, SubagentProfile } from '@/domain/agents'

import {
  buttonByText,
  deferred,
  getToastNotify,
  mountPrimaryPage,
  mountSubagentPage,
  resetAgentPageTestState,
  service,
} from './agentPages.testSupport'

beforeEach(resetAgentPageTestState)

describe('agent authoring pages', () => {
  it('updates a Primary only after loading its explicit UUID', async () => {
    const api = service()
    const id = '00000000-0000-0000-0000-000000000010'
    const { wrapper } = await mountPrimaryPage(
      api,
      `/agents/primary?id=${id}`,
    )
    expect(wrapper.text()).not.toContain(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.getPrimaryAgent).toHaveBeenCalledWith(id)
    expect(api.updatePrimaryAgent).toHaveBeenCalledWith(
      id,
      expect.objectContaining({ name: 'Shared name' }),
    )
    expect(api.createPrimaryAgent).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('loads a new Primary when only the route query UUID changes', async () => {
    const id = '00000000-0000-0000-0000-000000000011'
    const api = service({
      getPrimaryAgent: vi.fn(async (requestedId) => ({
        id: requestedId,
        name: 'Routed Primary',
        capability_refs: [],
        subagents: [],
      })),
    })
    const { router, wrapper } = await mountPrimaryPage(api)

    await router.push({ path: '/agents/primary', query: { id } })
    await flushPromises()

    expect(api.getPrimaryAgent).toHaveBeenCalledWith(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(api.updatePrimaryAgent).toHaveBeenCalledWith(
      id,
      expect.objectContaining({ name: 'Routed Primary' }),
    )
    wrapper.unmount()
  })

  it('keeps the latest Agent route when an earlier query load finishes late', async () => {
    const firstPrimaryId = '00000000-0000-0000-0000-000000000031'
    const secondPrimaryId = '00000000-0000-0000-0000-000000000032'
    const firstPrimary = deferred<PrimaryAgentProfile>()
    const secondPrimary = deferred<PrimaryAgentProfile>()
    const getPrimaryAgent = vi.fn((id: string) => (
      id === firstPrimaryId ? firstPrimary.promise : secondPrimary.promise
    ))
    const primaryApi = service({ getPrimaryAgent })
    const primaryPage = await mountPrimaryPage(primaryApi)

    await primaryPage.router.push({ path: '/agents/primary', query: { id: firstPrimaryId } })
    await primaryPage.router.push({ path: '/agents/primary', query: { id: secondPrimaryId } })
    await flushPromises()
    const primarySurface = primaryPage.wrapper.get('.configuration-loading-surface')
    expect(primarySurface.attributes('data-loading')).toBe('true')
    expect(primarySurface.attributes('inert')).toBeDefined()
    expect(primaryPage.wrapper.text()).not.toContain('common.loading')
    secondPrimary.resolve({
      id: secondPrimaryId,
      name: 'Latest Primary',
      capability_refs: [],
      subagents: [],
    })
    await flushPromises()
    expect(primarySurface.attributes('data-loading')).toBe('false')
    expect(primarySurface.attributes('inert')).toBeUndefined()
    firstPrimary.resolve({
      id: firstPrimaryId,
      name: 'Late Primary',
      capability_refs: [],
      subagents: [],
    })
    await flushPromises()
    await buttonByText(primaryPage.wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(primaryApi.updatePrimaryAgent).toHaveBeenCalledWith(
      secondPrimaryId,
      expect.objectContaining({ name: 'Latest Primary' }),
    )
    primaryPage.wrapper.unmount()

    const firstSubagentId = '00000000-0000-0000-0000-000000000041'
    const secondSubagentId = '00000000-0000-0000-0000-000000000042'
    const firstSubagent = deferred<SubagentProfile>()
    const secondSubagent = deferred<SubagentProfile>()
    const getSubagent = vi.fn((id: string) => (
      id === firstSubagentId ? firstSubagent.promise : secondSubagent.promise
    ))
    const subagentApi = service({ getSubagent })
    const subagentPage = await mountSubagentPage(subagentApi)

    await subagentPage.router.push({ path: '/agents/subagents', query: { id: firstSubagentId } })
    await subagentPage.router.push({ path: '/agents/subagents', query: { id: secondSubagentId } })
    await flushPromises()
    const subagentSurface = subagentPage.wrapper.get('.configuration-loading-surface')
    expect(subagentSurface.attributes('data-loading')).toBe('true')
    expect(subagentSurface.attributes('inert')).toBeDefined()
    expect(subagentPage.wrapper.text()).not.toContain('common.loading')
    secondSubagent.resolve({
      id: secondSubagentId,
      component_name: 'Latest Subagent',
      name: 'latest_worker',
      description: 'Latest worker.',
      settings: { capability_overrides: [], subagents: [] },
    })
    await flushPromises()
    expect(subagentSurface.attributes('data-loading')).toBe('false')
    expect(subagentSurface.attributes('inert')).toBeUndefined()
    firstSubagent.resolve({
      id: firstSubagentId,
      component_name: 'Late Subagent',
      name: 'late_worker',
      description: 'Late worker.',
      settings: { capability_overrides: [], subagents: [] },
    })
    await flushPromises()
    await buttonByText(subagentPage.wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(subagentApi.updateSubagent).toHaveBeenCalledWith(
      secondSubagentId,
      expect.objectContaining({ component_name: 'Latest Subagent' }),
    )
    subagentPage.wrapper.unmount()
  })

  it('keeps the loaded Primary identity when selecting another record fails', async () => {
    const currentId = '00000000-0000-0000-0000-000000000010'
    const failedId = '00000000-0000-0000-0000-000000000099'
    const api = service({
      listPrimaryAgents: vi.fn(async () => [
        {
          id: currentId,
          name: 'Current Primary',
          capability_refs: [],
          subagents: [],
        },
        {
          id: failedId,
          name: 'Unavailable Primary',
          capability_refs: [],
          subagents: [],
        },
      ]),
      getPrimaryAgent: vi.fn(async (id) => {
        if (id === failedId) throw new Error('load failed')
        return {
          id: currentId,
          name: 'Current Primary',
          capability_refs: [],
          subagents: [],
        }
      }),
    })
    const { wrapper } = await mountPrimaryPage(
      api,
      `/agents/primary?id=${currentId}`,
    )

    await wrapper.get('[data-testid="record-picker-select"]').setValue(failedId)
    await flushPromises()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.updatePrimaryAgent).toHaveBeenCalledWith(
      currentId,
      expect.objectContaining({ name: 'Current Primary' }),
    )
    expect(api.updatePrimaryAgent).not.toHaveBeenCalledWith(
      failedId,
      expect.anything(),
    )
    wrapper.unmount()
  })

  it('clears an old save error after the next Primary save succeeds', async () => {
    const createPrimaryAgent = vi.fn()
      .mockRejectedValueOnce(new ManagementApiError({
        status: 500,
        code: 'old_save_failure',
        message: 'The first save failed.',
      }))
      .mockResolvedValueOnce({
        id: 'created-primary',
        name: '',
        capability_refs: [],
        subagents: [],
      })
    const api = service({ createPrimaryAgent })
    const { wrapper } = await mountPrimaryPage(api)

    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('old_save_failure')

    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(getToastNotify()).toHaveBeenCalledWith({
      tone: 'success',
      title: 'agents.feedback.saved',
    })
    expect(wrapper.find('[data-testid="page-feedback"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('old_save_failure')
    wrapper.unmount()
  })
})
