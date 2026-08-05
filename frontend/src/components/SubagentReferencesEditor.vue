<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import {
  blankSubagentReference,
  type SubagentProfile,
  type SubagentReference,
} from '@/domain/agents'

const props = defineProps<{
  references: SubagentReference[]
  profiles: SubagentProfile[]
  pathPrefix?: string
}>()
const emit = defineEmits<{
  'update:references': [references: SubagentReference[]]
}>()

const { t } = useI18n()

function addReference(): void {
  emit('update:references', [...props.references, blankSubagentReference()])
}

function removeReference(index: number): void {
  emit('update:references', props.references.filter((_, itemIndex) => itemIndex !== index))
}

function updateReference(index: number, subagentId: string): void {
  emit('update:references', props.references.map((reference, itemIndex) => (
    itemIndex === index ? { subagent_id: subagentId } : reference
  )))
}

function profileFor(reference: SubagentReference): SubagentProfile | undefined {
  return props.profiles.find((profile) => profile.id === reference.subagent_id)
}
</script>

<template>
  <section class="card mb-3" aria-labelledby="subagent-references-title">
    <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
      <h2 id="subagent-references-title" class="card-title mb-0">
        {{ t('agents.primary.referencesTitle') }}
      </h2>
      <LteButton
        class="ms-auto"
        data-action="add-subagent-reference"
        :aria-label="t('agents.primary.addReference')"
        :title="t('agents.primary.addReference')"
        size="sm"
        theme="success"
        type="button"
        @click="addReference"
      >
        <i class="bi bi-plus-lg" aria-hidden="true" />
      </LteButton>
    </header>
    <div v-if="references.length === 0" class="card-body text-body-secondary">
      {{ t('agents.primary.noReferences') }}
    </div>
    <div v-else class="list-group list-group-flush">
      <div
        v-for="(reference, index) in references"
        :key="index"
        class="list-group-item"
        data-testid="subagent-reference-row"
      >
        <div class="d-flex align-items-center gap-2">
          <label class="visually-hidden" :for="`subagent-reference-${index}`">
            {{ t('agents.primary.reference') }}
          </label>
          <select
            :id="`subagent-reference-${index}`"
            class="form-select"
            data-testid="subagent-reference"
            :value="reference.subagent_id"
            @change="updateReference(index, ($event.target as HTMLSelectElement).value)"
          >
            <option disabled value="">{{ t('common.chooseConfiguration') }}</option>
            <option v-for="profile in profiles" :key="profile.id" :value="profile.id">
              {{ profile.component_name }} · {{ profile.name }}
            </option>
          </select>
          <LteButton
            class="ms-auto"
            data-action="remove-subagent-reference"
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
        <p v-if="profileFor(reference)" class="form-text mb-0">
          {{ profileFor(reference)?.description }}
        </p>
      </div>
    </div>
  </section>
</template>
