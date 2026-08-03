<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
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

function fieldPath(index: number): string {
  return `${props.pathPrefix ?? 'subagents'}.${index}.subagent_id`
}
</script>

<template>
  <section class="mb-3" aria-labelledby="subagent-references-title">
    <header class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
      <h2 id="subagent-references-title" class="h5 fw-semibold mb-0">
        {{ t('agents.primary.referencesTitle') }}
      </h2>
      <LteButton theme="success" type="button" @click="addReference">
        {{ t('agents.primary.addReference') }}
      </LteButton>
    </header>
    <p v-if="references.length === 0" class="text-body-secondary">
      {{ t('agents.primary.noReferences') }}
    </p>
    <article
      v-for="(reference, index) in references"
      :key="index"
      class="card mb-3"
      data-testid="subagent-reference-card"
    >
      <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
        <h3 class="card-title mb-0">
          {{ profileFor(reference)?.component_name || t('agents.primary.unselectedReference') }}
        </h3>
        <LteButton
          class="ms-auto"
          data-action="remove-subagent-reference"
          theme="danger"
          type="button"
          @click="removeReference(index)"
        >
          {{ t('common.remove') }}
        </LteButton>
      </header>
      <div class="card-body">
        <FormField :field-path="fieldPath(index)">
          <select
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
        </FormField>
        <p v-if="profileFor(reference)" class="form-text mb-0">
          {{ profileFor(reference)?.description }}
        </p>
      </div>
    </article>
  </section>
</template>
