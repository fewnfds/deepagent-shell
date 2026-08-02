import { effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ValidationReport } from '@/domain/agents'

import { useDraftValidation } from './useDraftValidation'

function report(valid: boolean): ValidationReport {
  return { valid, stage: 'draft_validation', issues: valid ? [] : [{
    code: 'invalid',
    scope: 'primary',
    owner_id: '',
    owner_name: '',
    path: 'name',
    message: 'invalid',
  }] }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('useDraftValidation', () => {
  it('debounces draft validation for 1000ms', async () => {
    vi.useFakeTimers()
    const draft = ref({ name: '' })
    const validate = vi.fn(async () => report(true))
    const scope = effectScope()
    const hook = scope.run(() => useDraftValidation(
      draft,
      () => ({ target: { kind: 'primary' }, payload: draft.value }),
      validate,
      { immediate: false },
    ))
    if (!hook) throw new Error('validation hook was not created')

    draft.value.name = 'next'
    await nextTick()
    await vi.advanceTimersByTimeAsync(999)
    expect(validate).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(validate).toHaveBeenCalledOnce()
    scope.stop()
  })

  it('suppresses an older response after a newer sequence completes', async () => {
    vi.useFakeTimers()
    const draft = ref({ name: '' })
    const pending: Array<(value: ValidationReport) => void> = []
    const validate = vi.fn(() => new Promise<ValidationReport>((resolve) => pending.push(resolve)))
    const scope = effectScope()
    const hook = scope.run(() => useDraftValidation(
      draft,
      () => ({ target: { kind: 'primary' }, payload: { ...draft.value } }),
      validate,
      { debounceMs: 0, immediate: false },
    ))
    if (!hook) throw new Error('validation hook was not created')

    hook.schedule(0)
    await vi.advanceTimersByTimeAsync(0)
    draft.value.name = 'newer'
    await nextTick()
    await vi.advanceTimersByTimeAsync(0)

    pending[1]?.(report(true))
    await Promise.resolve()
    expect(hook.validation.value.status).toBe('valid')

    pending[0]?.(report(false))
    await Promise.resolve()
    expect(hook.validation.value.status).toBe('valid')
    scope.stop()
  })
})
