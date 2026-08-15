<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import {
  blankMiddlewareReference,
  type MiddlewareReference,
  type StoredBlock,
} from '@/domain/agents'

const props = defineProps<{
  references: MiddlewareReference[]
  middlewares: StoredBlock[]
  idPrefix: string
}>()
const emit = defineEmits<{
  'update:references': [references: MiddlewareReference[]]
}>()

const { t } = useI18n()

function addReference(): void {
  emit('update:references', [...props.references, blankMiddlewareReference()])
}

function updateReference(index: number, middlewareId: string): void {
  emit('update:references', props.references.map((reference, itemIndex) => (
    itemIndex === index ? { middleware_id: middlewareId } : reference
  )))
}

function removeReference(index: number): void {
  emit('update:references', props.references.filter((_, itemIndex) => itemIndex !== index))
}

function moveReference(index: number, offset: -1 | 1): void {
  const target = index + offset
  if (target < 0 || target >= props.references.length) return
  const next = [...props.references]
  ;[next[index], next[target]] = [next[target]!, next[index]!]
  emit('update:references', next)
}

function optionDisabled(middlewareId: string, index: number): boolean {
  return props.references.some((reference, itemIndex) => (
    itemIndex !== index && reference.middleware_id === middlewareId
  ))
}
</script>

<template>
  <section class="card mb-3" :aria-labelledby="`${idPrefix}-title`">
    <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
      <h2 :id="`${idPrefix}-title`" class="card-title mb-0">
        {{ t('agents.middleware.referencesTitle') }}
      </h2>
      <LteButton
        class="ms-auto"
        data-action="add-middleware-reference"
        :aria-label="t('agents.middleware.addReference')"
        :title="t('agents.middleware.addReference')"
        size="sm"
        theme="success"
        type="button"
        @click="addReference"
      >
        <i class="bi bi-plus-lg" aria-hidden="true" />
      </LteButton>
    </header>
    <div v-if="references.length === 0" class="card-body text-body-secondary">
      {{ t('agents.middleware.noReferences') }}
    </div>
    <div v-else class="card-body">
      <div class="row g-3">
        <div
          v-for="(reference, index) in references"
          :key="index"
          class="col-md-6 col-lg-4"
          data-testid="middleware-reference-row"
        >
          <div class="border rounded p-3 h-100">
            <div class="d-flex align-items-center gap-2 mb-2">
              <span class="badge text-bg-secondary">{{ index + 1 }}</span>
              <div class="d-flex gap-1 ms-auto" role="group">
                <LteButton
                  data-action="move-middleware-reference-up"
                  :aria-label="t('common.moveUp')"
                  :title="t('common.moveUp')"
                  :disabled="index === 0"
                  size="sm"
                  theme="secondary"
                  type="button"
                  @click="moveReference(index, -1)"
                >
                  <i class="bi bi-arrow-up" aria-hidden="true" />
                </LteButton>
                <LteButton
                  data-action="move-middleware-reference-down"
                  :aria-label="t('common.moveDown')"
                  :title="t('common.moveDown')"
                  :disabled="index === references.length - 1"
                  size="sm"
                  theme="secondary"
                  type="button"
                  @click="moveReference(index, 1)"
                >
                  <i class="bi bi-arrow-down" aria-hidden="true" />
                </LteButton>
                <LteButton
                  data-action="remove-middleware-reference"
                  :aria-label="t('common.remove')"
                  :title="t('common.remove')"
                  size="sm"
                  theme="danger"
                  type="button"
                  @click="removeReference(index)"
                >
                  <i class="bi bi-trash" aria-hidden="true" />
                </LteButton>
              </div>
            </div>
            <label class="visually-hidden" :for="`${idPrefix}-${index}`">
              {{ t('agents.middleware.reference') }}
            </label>
            <select
              :id="`${idPrefix}-${index}`"
              class="form-select"
              data-testid="middleware-reference"
              :value="reference.middleware_id"
              @change="updateReference(index, ($event.target as HTMLSelectElement).value)"
            >
              <option disabled value="">{{ t('common.chooseConfiguration') }}</option>
              <option
                v-for="middleware in middlewares"
                :key="middleware.id"
                :disabled="optionDisabled(middleware.id, index)"
                :value="middleware.id"
              >
                {{ middleware.name }}
              </option>
            </select>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
