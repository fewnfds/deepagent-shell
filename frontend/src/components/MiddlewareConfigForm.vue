<script setup lang="ts">
import { computed } from 'vue'

import type {
  MiddlewareConfigField,
  MiddlewareConfigScalar,
  MiddlewareConfigSchema,
} from '@/api'

const props = defineProps<{
  idPrefix: string
  modelValue: Record<string, unknown>
  schema: MiddlewareConfigSchema
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
}>()

const fields = computed(() => Object.entries(props.schema.properties))
const required = computed(() => new Set(props.schema.required))

function updateField(name: string, value: unknown): void {
  const next = { ...props.modelValue }
  if (value === undefined) delete next[name]
  else next[name] = value
  emit('update:modelValue', next)
}

function textValue(name: string): string {
  const value = props.modelValue[name]
  return typeof value === 'string' ? value : ''
}

function numberValue(name: string): number | '' {
  const value = props.modelValue[name]
  return typeof value === 'number' ? value : ''
}

function updateNumber(name: string, event: Event): void {
  const input = event.target as HTMLInputElement
  updateField(name, input.value === '' ? undefined : input.valueAsNumber)
}

function enumIndex(name: string, field: MiddlewareConfigField): string {
  const index = field.enum?.findIndex((value) => Object.is(value, props.modelValue[name])) ?? -1
  return index < 0 ? '' : String(index)
}

function updateEnum(name: string, field: MiddlewareConfigField, event: Event): void {
  const selected = (event.target as HTMLSelectElement).value
  updateField(name, selected === '' ? undefined : field.enum?.[Number(selected)])
}

function optionLabel(value: MiddlewareConfigScalar): string {
  return String(value)
}
</script>

<template>
  <div v-if="fields.length" class="row g-3">
    <div v-for="([name, field]) in fields" :key="name" class="col-12 management-control-field">
      <template v-if="field.enum">
        <label class="form-label" :for="`${idPrefix}-${name}`">{{ field.title }}</label>
        <div class="management-control">
          <select
            :id="`${idPrefix}-${name}`"
            class="form-select"
            :required="required.has(name)"
            :value="enumIndex(name, field)"
            @change="updateEnum(name, field, $event)"
          >
            <option v-if="!required.has(name)" value="" />
            <option
              v-for="(option, index) in field.enum"
              :key="`${typeof option}-${String(option)}`"
              :value="String(index)"
            >
              {{ optionLabel(option) }}
            </option>
          </select>
        </div>
      </template>

      <template v-else-if="field.type === 'boolean'">
        <span class="form-label">{{ field.title }}</span>
        <div class="management-control">
          <div class="form-check form-switch">
            <input
              :id="`${idPrefix}-${name}`"
              class="form-check-input"
              role="switch"
              type="checkbox"
              :checked="modelValue[name] === true"
              @change="updateField(name, ($event.target as HTMLInputElement).checked)"
            >
            <label class="visually-hidden" :for="`${idPrefix}-${name}`">{{ field.title }}</label>
          </div>
        </div>
      </template>

      <template v-else-if="field.type === 'integer' || field.type === 'number'">
        <label class="form-label" :for="`${idPrefix}-${name}`">{{ field.title }}</label>
        <div class="management-control">
          <input
            :id="`${idPrefix}-${name}`"
            class="form-control"
            :max="field.maximum"
            :min="field.minimum"
            :required="required.has(name)"
            :step="field.type === 'integer' ? 1 : 'any'"
            type="number"
            :value="numberValue(name)"
            @input="updateNumber(name, $event)"
          >
        </div>
      </template>

      <template v-else-if="field.format === 'python'">
        <label class="form-label" :for="`${idPrefix}-${name}`">{{ field.title }}</label>
        <div class="management-control">
          <textarea
            :id="`${idPrefix}-${name}`"
            class="form-control font-monospace"
            :maxlength="field.maxLength"
            :minlength="field.minLength"
            :pattern="field.pattern"
            :required="required.has(name)"
            rows="1"
            spellcheck="false"
            :value="textValue(name)"
            @input="updateField(name, ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
      </template>

      <template v-else>
        <label class="form-label" :for="`${idPrefix}-${name}`">{{ field.title }}</label>
        <div class="management-control">
          <textarea
            :id="`${idPrefix}-${name}`"
            class="form-control"
            :maxlength="field.maxLength"
            :minlength="field.minLength"
            :pattern="field.pattern"
            :required="required.has(name)"
            rows="1"
            :value="textValue(name)"
            @input="updateField(name, ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
      </template>

      <div v-if="field.description" class="form-text">{{ field.description }}</div>
    </div>
  </div>
</template>
