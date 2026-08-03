import {
  onScopeDispose,
  readonly,
  ref,
  watch,
  type DeepReadonly,
  type Ref,
  type WatchSource,
} from 'vue'

import type { DraftValidationRequest, ValidationReport } from '@/domain/agents'

const DRAFT_VALIDATION_DEBOUNCE_MS = 1000

type DraftValidationStatus = 'unavailable' | 'validating' | 'valid' | 'invalid'

export interface DraftValidationState {
  status: DraftValidationStatus
  report: ValidationReport | null
  error: string
}

type DraftValidator = (request: DraftValidationRequest) => Promise<ValidationReport>

interface DraftValidationOptions {
  debounceMs?: number
  immediate?: boolean
}

function state(status: DraftValidationStatus, report: ValidationReport | null = null, error = ''): DraftValidationState {
  return { status, report, error }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function useDraftValidation(
  source: WatchSource<unknown>,
  buildRequest: () => DraftValidationRequest | null,
  validate: DraftValidator,
  options: DraftValidationOptions = {},
): {
  validation: DeepReadonly<Ref<DraftValidationState>>
  schedule: (delay?: number) => void
  validateNow: () => Promise<DraftValidationState>
} {
  const debounceMs = options.debounceMs ?? DRAFT_VALIDATION_DEBOUNCE_MS
  const validation = ref<DraftValidationState>(state('unavailable'))
  let timer: ReturnType<typeof setTimeout> | undefined
  let sequence = 0

  async function run(currentSequence: number): Promise<DraftValidationState> {
    let request: DraftValidationRequest | null
    try {
      request = buildRequest()
      if (!request) {
        if (currentSequence === sequence) validation.value = state('unavailable')
        return validation.value
      }
    } catch (error) {
      if (currentSequence === sequence) validation.value = state('unavailable', null, errorMessage(error))
      return validation.value
    }

    try {
      const report = await validate(request)
      if (currentSequence === sequence) {
        validation.value = state(report.valid ? 'valid' : 'invalid', report)
      }
    } catch (error) {
      if (currentSequence === sequence) validation.value = state('unavailable', null, errorMessage(error))
    }
    return validation.value
  }

  function schedule(delay = debounceMs): void {
    sequence += 1
    const currentSequence = sequence
    if (timer !== undefined) clearTimeout(timer)
    validation.value = state('validating')
    timer = setTimeout(() => {
      timer = undefined
      void run(currentSequence)
    }, delay)
  }

  async function validateNow(): Promise<DraftValidationState> {
    sequence += 1
    const currentSequence = sequence
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
    validation.value = state('validating')
    return run(currentSequence)
  }

  watch(source, () => schedule(), {
    deep: true,
    immediate: options.immediate ?? true,
  })

  onScopeDispose(() => {
    sequence += 1
    if (timer !== undefined) clearTimeout(timer)
  })

  return {
    validation: readonly(validation),
    schedule,
    validateNow,
  }
}
