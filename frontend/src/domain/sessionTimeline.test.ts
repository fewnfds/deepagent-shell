import { describe, expect, it } from 'vitest'

import type { AgentSessionTimeline, AgentSessionTimelineRun } from '@/api'

import { buildSessionTimeline } from './sessionTimeline'

function run(id: string, timeline: AgentSessionTimelineRun['timeline']): AgentSessionTimelineRun {
  return {
    id,
    session_id: 'session-1',
    request_id: `request-${id}`,
    model: 'public-model',
    agent_name: 'Primary',
    started_at: '2026-01-02T03:04:00Z',
    finished_at: '2026-01-02T03:04:05Z',
    status: 'completed',
    error_code: null,
    input_message_count: 0,
    timeline,
    response_summary: 'done',
  }
}

describe('session Timeline projection', () => {
  it('keeps tool and Subagent events on the latest model-request number across runs', () => {
    const session: AgentSessionTimeline = {
      session_id: 'session-1',
      token_usage: {
        input_tokens: 0,
        non_reasoning_output_tokens: 0,
        reasoning_output_tokens: 0,
      },
      runs: [
        run('one', [
          { step_id: 'event-0', sequence: 1, kind: 'lifecycle', timestamp: null, data: { status: 'running' } },
          { step_id: 'event-1', sequence: 2, kind: 'agent_input', timestamp: null, data: { agent_type: 'primary' } },
          { step_id: 'event-2', sequence: 3, kind: 'model_request', timestamp: null, data: { message_count: 0 } },
          { step_id: 'event-3', sequence: 4, kind: 'model_response', timestamp: null, data: { provider_finish_reason: 'tool_calls' } },
          { step_id: 'event-4', sequence: 5, kind: 'tool_call', timestamp: null, data: { tool_name: 'read_file' } },
          { step_id: 'event-5', sequence: 6, kind: 'context_worker', timestamp: null, data: { worker_name: 'Analyst', phase: 'start' } },
          { step_id: 'event-6', sequence: 7, kind: 'tool_result', timestamp: null, data: { tool_name: 'read_file' } },
          { step_id: 'event-7', sequence: 8, kind: 'model_request', timestamp: null, data: { message_count: 0 } },
          { step_id: 'event-8', sequence: 9, kind: 'subagent', timestamp: null, data: { subagent_name: 'Researcher' } },
        ]),
        run('two', [
          { step_id: 'event-0', sequence: 1, kind: 'model_request', timestamp: null, data: { message_count: 0 } },
          { step_id: 'event-1', sequence: 2, kind: 'tool_error', timestamp: null, data: { tool_name: 'write_file' } },
        ]),
      ],
    }

    const entries = buildSessionTimeline(session)

    expect(entries.map((entry) => [entry.kind, entry.modelRequestNumber])).toEqual([
      ['request_input', null],
      ['agent_input', null],
      ['model_request', 1],
      ['model_response', 1],
      ['tool_call', 1],
      ['context_worker', 1],
      ['tool_result', 1],
      ['model_request', 2],
      ['subagent', 2],
      ['request_output', 2],
      ['request_input', null],
      ['model_request', 3],
      ['tool_error', 3],
      ['request_output', 3],
    ])
  })

  it('does not invent a model-request number when a request ends before calling a model', () => {
    const session: AgentSessionTimeline = {
      session_id: 'session-1',
      token_usage: {
        input_tokens: null,
        non_reasoning_output_tokens: null,
        reasoning_output_tokens: null,
      },
      runs: [run('failed', [{
        step_id: 'event-0',
        sequence: 1,
        kind: 'lifecycle',
        timestamp: null,
        data: { status: 'failed' },
      }])],
    }

    expect(buildSessionTimeline(session).map((entry) => entry.modelRequestNumber)).toEqual([
      null,
      null,
    ])
  })
})
