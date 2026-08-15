<script setup lang="ts">
import { LteAlert, LteButton, LteTextarea } from '@adminlte/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  LocalizedMessagePayload,
  PythonPackageFile,
  PythonPackageTemplate,
} from '@/api'
import {
  applyEmptyPythonPackageTemplate,
  applyPythonPackageTemplate,
  EMPTY_PYTHON_PACKAGE_TEMPLATE_KEY,
  type PythonPackageDraftState,
} from '@/domain/blocks/pythonPackage'
import { useEditorModel } from '@/editors/shared/useEditorModel'

const props = withDefaults(defineProps<{
  modelValue: PythonPackageDraftState
  saved: boolean
  catalog?: PythonPackageTemplate[]
  errors?: Record<string, LocalizedMessagePayload>
  loading?: boolean
  idPrefix: string
}>(), {
  catalog: () => [],
  errors: () => ({}),
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: PythonPackageDraftState]
  'load-files': [paths: string[]]
  refresh: []
}>()

const { t } = useI18n()
const draft = useEditorModel(
  () => props.modelValue,
  (value) => emit('update:modelValue', value),
)

const selectedTemplate = computed(() => props.catalog.find(
  (item) => item.key === draft.python_package_files.template_key,
))

function selectTemplate(key: string): void {
  if (key === EMPTY_PYTHON_PACKAGE_TEMPLATE_KEY) {
    applyEmptyTemplate()
    return
  }
  applyPythonPackageTemplate(draft, props.catalog.find((item) => item.key === key))
}

function applyEmptyTemplate(): void {
  applyEmptyPythonPackageTemplate(draft)
}

function templateFile(path: string): PythonPackageFile | undefined {
  return selectedTemplate.value?.files.find((file) => file.path === path)
}

function isRelativePath(path: string): boolean {
  return Boolean(path)
    && !path.startsWith('/')
    && !path.startsWith('\\')
    && !path.includes('\\')
    && !path.includes(':')
    && !path.split('/').some((part) => !part || part === '.' || part === '..')
    && path.split('/')[0]?.toLowerCase() !== 'package.json'
}

function updateEditablePaths(): void {
  const paths = draft.editable_paths_source
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter((value, index, values) => value !== '' && values.indexOf(value) === index)
  const current = new Map(draft.python_package_files.files.map((file) => [file.path, file]))
  const newPaths = paths.filter((path) => isRelativePath(path) && !current.has(path))
  draft.python_package.editable_files = paths
  draft.python_package_files.files = paths.map((path) => {
    const existing = current.get(path)
    if (existing) return existing
    const fromTemplate = templateFile(path)
    return fromTemplate
      ? {
        path,
        content: fromTemplate.content,
        exists: fromTemplate.exists !== false,
        readable: fromTemplate.readable !== false,
      }
      : {
        path,
        content: '',
        ...(props.saved ? {} : { exists: false }),
        readable: true,
      }
  })
  if (props.saved && newPaths.length) emit('load-files', newPaths)
}

function pathWarning(file: PythonPackageFile): string {
  if (!isRelativePath(file.path)) return t('editors.pythonPackage.pathInvalid')
  if (file.exists === false) return t('editors.pythonPackage.fileMissing')
  if (file.readable === false) return t('editors.pythonPackage.fileUnreadable')
  return ''
}

function resourceError(error: LocalizedMessagePayload): string {
  return t(error.message_key, error.message_args)
}
</script>

<template>
  <section class="card mb-3">
    <header class="card-header d-flex align-items-center gap-2">
      <h3 class="card-title h5 mb-0">{{ t('editors.pythonPackage.title') }}</h3>
      <LteButton
        v-if="!saved"
        class="ms-auto"
        :aria-label="t('editors.common.refresh')"
        :disabled="loading"
        size="sm"
        theme="info"
        type="button"
        @click="emit('refresh')"
      >
        <i class="bi bi-arrow-clockwise" aria-hidden="true" />
      </LteButton>
    </header>
    <div class="card-body">
      <template v-if="!saved">
        <label class="form-label" :for="`${idPrefix}-template`">
          {{ t('editors.pythonPackage.template') }}
        </label>
        <div class="input-group">
          <select
            :id="`${idPrefix}-template`"
            class="form-select"
            :value="draft.python_package_files.template_key"
            @change="selectTemplate(($event.target as HTMLSelectElement).value)"
          >
            <option value="">{{ t('editors.pythonPackage.selectTemplate') }}</option>
            <option :value="EMPTY_PYTHON_PACKAGE_TEMPLATE_KEY">{{ t('editors.pythonPackage.emptyTemplate') }}</option>
            <option v-for="item in catalog" :key="item.key" :value="item.key">
              {{ item.name }} ({{ item.key }})
            </option>
          </select>
          <LteButton theme="secondary" type="button" @click="applyEmptyTemplate">
            {{ t('editors.pythonPackage.applyEmptyTemplate') }}
          </LteButton>
        </div>
      </template>

      <LteAlert
        v-if="draft.python_package_error"
        class="mt-3 mb-0"
        theme="danger"
        :title="resourceError(draft.python_package_error)"
      />

      <template v-if="draft.python_package_files.files.length || draft.python_package_files.template_key">
        <div class="mt-3">
          <label class="form-label" :for="`${idPrefix}-paths`">
            {{ t('editors.pythonPackage.files') }}
          </label>
          <textarea
            :id="`${idPrefix}-paths`"
            v-model="draft.editable_paths_source"
            class="form-control font-monospace"
            rows="2"
            spellcheck="false"
            @change="updateEditablePaths"
          />
          <div class="form-text">{{ t('editors.pythonPackage.filesHint') }}</div>
        </div>

        <div
          v-for="(file, index) in draft.python_package_files.files"
          :key="`${file.path}-${index}`"
          class="mt-3"
        >
          <label class="form-label" :for="`${idPrefix}-file-${index}`">{{ file.path }}</label>
          <LteTextarea
            :id="`${idPrefix}-file-${index}`"
            v-model="file.content"
            class="font-monospace"
            :rows="18"
            spellcheck="false"
          />
          <LteAlert
            v-if="pathWarning(file)"
            class="mt-2 mb-0"
            theme="warning"
            :title="pathWarning(file)"
          />
        </div>

        <LteAlert
          v-if="saved && draft.dependency_status && draft.dependency_status !== 'ready'"
          class="mt-3 mb-0"
          theme="info"
          :title="t(`editors.pythonPackage.status.${draft.dependency_status}`)"
        />
      </template>
    </div>
    <div v-if="Object.keys(errors).length" class="card-body">
      <div class="alert alert-danger mb-0" role="alert">
        <p v-for="(error, folder) in errors" :key="folder" class="mb-1">
          <strong>{{ folder }}</strong> {{ resourceError(error) }}
        </p>
      </div>
    </div>
  </section>
</template>
