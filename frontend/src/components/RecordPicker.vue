<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'

interface RecordOption {
  id: string
  name: string
}

withDefaults(defineProps<{
  disabled?: boolean
  modelValue: string
  name: string
  records: readonly RecordOption[]
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  select: [value: string]
  'update:name': [value: string]
}>()

const { t } = useI18n()

function selectRecord(event: Event): void {
  emit('select', (event.target as HTMLSelectElement).value)
}

function updateName(event: Event): void {
  emit('update:name', (event.target as HTMLInputElement).value)
}
</script>

<template>
  <section class="row g-3">
    <div class="col-md-6">
      <FormField field-path="id" label-key="common.recordPicker.load">
        <select
          class="form-select"
          data-testid="record-picker-select"
          :disabled="disabled"
          :value="modelValue"
          @change="selectRecord"
        >
          <option value="">{{ t('common.recordPicker.newOption') }}</option>
          <option v-for="record in records" :key="record.id" :value="record.id">
            {{ record.name }}
          </option>
        </select>
      </FormField>
    </div>
    <div class="col-md-6">
      <FormField field-path="name" label-key="common.recordPicker.name">
        <input
          autocomplete="off"
          class="form-control"
          data-field="record-name"
          :disabled="disabled"
          :value="name"
          @input="updateName"
        >
      </FormField>
    </div>
  </section>
</template>
