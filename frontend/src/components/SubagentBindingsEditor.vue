<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import {
  blankSubagentBinding,
  type SubagentBinding,
  type SubagentOverrideProfile,
} from '@/domain/agents'

const props = defineProps<{
  bindings: SubagentBinding[]
  overrideProfiles: SubagentOverrideProfile[]
}>()
const emit = defineEmits<{
  'update:bindings': [bindings: SubagentBinding[]]
}>()

const { t } = useI18n()

function addBinding(): void {
  emit('update:bindings', [...props.bindings, blankSubagentBinding()])
}

function removeBinding(index: number): void {
  emit('update:bindings', props.bindings.filter((_, bindingIndex) => bindingIndex !== index))
}

function inputValue(event: Event): string {
  return (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value
}

function updateBinding(index: number, patch: Partial<SubagentBinding>): void {
  emit('update:bindings', props.bindings.map((binding, bindingIndex) => (
    bindingIndex === index ? { ...binding, ...patch } : binding
  )))
}
</script>

<template>
  <section class="mb-3" aria-labelledby="subagent-bindings-title">
    <header class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
      <h2 id="subagent-bindings-title" class="h5 fw-semibold mb-0">
        {{ t('agents.primary.bindingsTitle') }}
      </h2>
      <LteButton theme="success" type="button" @click="addBinding">
        {{ t('agents.primary.addBinding') }}
      </LteButton>
    </header>
    <p v-if="bindings.length === 0" class="text-body-secondary">
      {{ t('agents.primary.noBindings') }}
    </p>
    <article
      v-for="(binding, index) in bindings"
      :key="index"
      class="card mb-3"
      data-testid="binding-card"
    >
      <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
        <h3 class="card-title mb-0">
          {{ binding.name || t('agents.primary.unnamedBinding') }}
        </h3>
        <LteButton
          class="ms-auto"
          data-action="remove-binding"
          theme="danger"
          type="button"
          @click="removeBinding(index)"
        >
          {{ t('common.remove') }}
        </LteButton>
      </header>
      <div class="card-body" data-testid="binding-body">
        <div class="row g-3">
          <div class="col-md-6">
            <FormField :field-path="`subagents.${index}.name`">
              <input
                autocomplete="off"
                class="form-control"
                :value="binding.name"
                @input="updateBinding(index, { name: inputValue($event) })"
              >
            </FormField>
          </div>
          <div class="col-md-6">
            <FormField :field-path="`subagents.${index}.subagent_override_id`">
              <select
                class="form-select"
                data-testid="binding-override"
                :value="binding.subagent_override_id"
                @change="updateBinding(index, { subagent_override_id: inputValue($event) })"
              >
                <option value="">{{ t('agents.primary.inheritPrimary') }}</option>
                <option v-for="profile in overrideProfiles" :key="profile.id" :value="profile.id">
                  {{ profile.name }}
                </option>
              </select>
            </FormField>
          </div>
          <div class="col-12">
            <FormField :field-path="`subagents.${index}.description`">
              <textarea
                class="form-control"
                rows="4"
                :value="binding.description"
                @input="updateBinding(index, { description: inputValue($event) })"
              />
            </FormField>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>
