import { describe, expect, it } from 'vitest'

import {
  blankPrimaryAgent,
  blankSubagentOverride,
  blankWorkerProfile,
  normalizeSubagentBinding,
  overrideSelection,
  primaryAgentPayload,
  setOverrideSelection,
  setReference,
  setWorkerOverrideSelection,
  subagentOverridePayload,
  workerOverrideSelection,
  workerProfilePayload,
} from './agents'

describe('agent profile adapters', () => {
  it('keeps explicit UUID references and never derives them from names', () => {
    const draft = blankPrimaryAgent()
    draft.name = 'Repeated display name'
    setReference(draft, 'model', '00000000-0000-0000-0000-000000000001')
    draft.capability_refs.push({ type: 'unknown', block_id: 'discarded' })

    expect(primaryAgentPayload(draft)).toEqual({
      name: 'Repeated display name',
      capability_refs: [{
        type: 'model',
        block_id: '00000000-0000-0000-0000-000000000001',
      }, { type: 'unknown', block_id: 'discarded' }],
      subagents: [],
      workers: [],
    })
  })

  it('stores Context Worker component choices independently from Subagent overrides', () => {
    const draft = blankWorkerProfile()
    draft.include_client_messages = false
    setWorkerOverrideSelection(draft, 'model', 'replace', '00000000-0000-0000-0000-000000000003')
    expect(workerOverrideSelection(draft, 'model').mode).toBe('replace')
    expect(workerProfilePayload(draft)).toEqual({
      name: '',
      include_client_messages: false,
      capability_overrides: [{
        type: 'model', mode: 'replace', block_id: '00000000-0000-0000-0000-000000000003',
      }],
    })
  })

  it('stores only explicit replace or disabled override entries', () => {
    const draft = blankSubagentOverride()
    setOverrideSelection(draft, 'model', 'replace', '00000000-0000-0000-0000-000000000002')
    expect(overrideSelection(draft, 'model').mode).toBe('replace')

    setOverrideSelection(draft, 'model', 'inherit')
    expect(overrideSelection(draft, 'model').mode).toBe('inherit')
    expect(subagentOverridePayload(draft).capability_overrides).toEqual([])
  })

  it('projects Subagent bindings without the removed enabled field', () => {
    expect(normalizeSubagentBinding({
      enabled: false,
      name: 'researcher',
      description: 'Research delegated topics',
      subagent_override_id: '',
    })).toEqual({
      name: 'researcher',
      description: 'Research delegated topics',
      subagent_override_id: '',
    })
  })
})
