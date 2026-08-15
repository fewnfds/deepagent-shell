<script setup lang="ts">
import type { LocalizedMessagePayload } from '@/api'
import PythonPackageEditor from '@/components/PythonPackageEditor.vue'
import {
  type ConditionRouterCatalogItem,
  type ConditionRouterDefaults,
  type ConditionRouterDraft,
} from '@/domain/blocks'
import type { PythonPackageDraftState } from '@/domain/blocks/pythonPackage'
import { useEditorModel } from './shared/useEditorModel'

const props = withDefaults(defineProps<{
  modelValue: ConditionRouterDraft
  defaults?: ConditionRouterDefaults
  catalog?: ConditionRouterCatalogItem[]
  errors?: Record<string, LocalizedMessagePayload>
  loading?: boolean
}>(), {
  catalog: () => [],
  errors: () => ({}),
  loading: false,
})
const emit = defineEmits<{
  'update:modelValue': [value: ConditionRouterDraft]
  refresh: []
}>()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function updatePackage(value: PythonPackageDraftState): void {
  draft.python_package = value.python_package
  draft.python_package_files = value.python_package_files
  draft.python_package_manifest = value.python_package_manifest
  draft.dependency_status = value.dependency_status
}
</script>

<template>
  <div data-editor="condition-router">
    <PythonPackageEditor
      :catalog="catalog"
      :errors="errors"
      id-prefix="condition-router"
      :loading="loading"
      :model-value="draft"
      :saved="Boolean(draft.id)"
      @refresh="emit('refresh')"
      @update:model-value="updatePackage"
    />
  </div>
</template>
