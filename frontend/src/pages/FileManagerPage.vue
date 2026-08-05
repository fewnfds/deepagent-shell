<script setup lang="ts">
import { LteAlert, LteButton, LteCard, LteProgress } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  ManagementApiError,
  managementApi,
  type FileManagerScope,
  type ManagedArchivePreview,
  type ManagedDirectory,
  type ManagedFileScopeCatalog,
  type ManagedFileItem,
  type ManagedTextFile,
} from '@/api'
import ModalHost from '@/components/ModalHost.vue'
import PageShell from '@/components/PageShell.vue'
import { useConfirmation } from '@/composables/useConfirmation'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { formattingLocale } from '@/locales'
import { triggerBrowserDownload } from '@/utils/download'

interface FileManagerApi {
  listManagedFileScopes(): Promise<ManagedFileScopeCatalog>
  listManagedFiles(scope: FileManagerScope, path?: string): Promise<ManagedDirectory>
  createManagedDirectory(scope: FileManagerScope, path: string): Promise<{ path: string }>
  createManagedTextFile(scope: FileManagerScope, path: string): Promise<{ path: string }>
  uploadManagedFile(
    scope: FileManagerScope,
    path: string,
    file: Blob,
    overwrite: boolean,
    onProgress?: (loaded: number, total: number) => void,
  ): Promise<{ path: string }>
  downloadManagedEntry(scope: FileManagerScope, path: string): Promise<Blob>
  previewManagedArchive(scope: FileManagerScope, paths: string[]): Promise<ManagedArchivePreview>
  downloadManagedArchive(scope: FileManagerScope, paths: string[]): Promise<Blob>
  readManagedTextFile(scope: FileManagerScope, path: string): Promise<ManagedTextFile>
  saveManagedTextFile(
    scope: FileManagerScope,
    path: string,
    content: string,
    revision: string,
  ): Promise<{ path: string; revision: string }>
  renameManagedEntry(
    scope: FileManagerScope,
    path: string,
    name: string,
  ): Promise<{ path: string }>
  deleteManagedFile(scope: FileManagerScope, path: string): Promise<{ deleted: boolean }>
}

interface UploadItem {
  id: string
  file: File
  path: string
  progress: number
  status: 'pending' | 'uploading' | 'completed' | 'failed'
  error: string
}

const props = defineProps<{ api?: FileManagerApi }>()
const api = props.api ?? managementApi
const { locale, t } = useI18n()
const confirmation = useConfirmation()
const managementError = useManagementError()
const { notify } = useToasts()

const scopes = ref<FileManagerScope[]>([])
const scope = ref<FileManagerScope>('files')
const atManagerRoot = ref(true)
const directory = ref<ManagedDirectory>({ scope: 'files', path: '', items: [] })
const loading = ref(true)
const pageError = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const uploads = ref<UploadItem[]>([])
const uploading = ref(false)
const selectedItems = ref<ManagedFileItem[]>([])
const archiveDownloading = ref(false)
const createOpen = ref(false)
const createKind = ref<'directory' | 'file'>('directory')
const createName = ref('')
const createSaving = ref(false)
const renameOpen = ref(false)
const renamingItem = ref<ManagedFileItem | null>(null)
const renameName = ref('')
const renameSaving = ref(false)
const editorOpen = ref(false)
const editorPath = ref('')
const editorContent = ref('')
const editorRevision = ref('')
const editorLoading = ref(false)
const editorSaving = ref(false)
const editorError = ref('')
let directoryRequestSequence = 0
let requestedDirectoryPath = ''
let editorRequestSequence = 0

const breadcrumbs = computed(() => {
  const result: Array<{ label: string, path: string | null }> = [
    { label: t('fileManager.title'), path: null },
    { label: scope.value, path: '' },
  ]
  const parts = directory.value.path ? directory.value.path.split('/') : []
  parts.forEach((part, index) => {
    result.push({ label: part, path: parts.slice(0, index + 1).join('/') })
  })
  return result
})
const selectableItems = computed(() => directory.value.items.filter(canSelect))
const allSelected = computed(() => (
  selectableItems.value.length > 0
  && selectableItems.value.every((item) => selectedItems.value.some((selected) => selected.path === item.path))
))

function joinPath(base: string, child: string): string {
  return base ? `${base}/${child}` : child
}

function isCurrentDirectoryRequest(
  requestSequence: number,
  requestedScope: FileManagerScope,
  path: string,
): boolean {
  return requestSequence === directoryRequestSequence
    && !atManagerRoot.value
    && scope.value === requestedScope
    && requestedDirectoryPath === path
}

function isCurrentEditorRequest(
  requestSequence: number,
  requestedScope: FileManagerScope,
  path: string,
): boolean {
  return requestSequence === editorRequestSequence
    && editorOpen.value
    && scope.value === requestedScope
    && editorPath.value === path
}

async function load(path = directory.value.path): Promise<void> {
  const requestSequence = ++directoryRequestSequence
  const requestedScope = scope.value
  requestedDirectoryPath = path
  loading.value = true
  pageError.value = ''
  selectedItems.value = []
  try {
    const response = await api.listManagedFiles(requestedScope, path)
    if (!isCurrentDirectoryRequest(requestSequence, requestedScope, path)) return
    directory.value = response
  } catch (error) {
    if (!isCurrentDirectoryRequest(requestSequence, requestedScope, path)) return
    pageError.value = managementError.describe(error).display
  } finally {
    if (isCurrentDirectoryRequest(requestSequence, requestedScope, path)) loading.value = false
  }
}

async function loadScopes(): Promise<void> {
  directoryRequestSequence += 1
  loading.value = true
  pageError.value = ''
  uploads.value = []
  selectedItems.value = []
  try {
    const catalog = await api.listManagedFileScopes()
    scopes.value = catalog.scopes
    atManagerRoot.value = true
  } catch (error) {
    scopes.value = []
    pageError.value = managementError.describe(error).display
  } finally {
    loading.value = false
  }
}

function openScope(value: FileManagerScope): void {
  scope.value = value
  atManagerRoot.value = false
  directory.value = { scope: value, path: '', items: [] }
  uploads.value = []
  selectedItems.value = []
  void load('')
}

function navigateBreadcrumb(path: string | null): void {
  if (path === null) {
    directoryRequestSequence += 1
    atManagerRoot.value = true
    loading.value = false
    uploads.value = []
    selectedItems.value = []
    return
  }
  void load(path)
}

function openCreate(kind: 'directory' | 'file'): void {
  createKind.value = kind
  createName.value = ''
  createOpen.value = true
}

async function createEntry(): Promise<void> {
  const name = createName.value.trim()
  if (!name) return
  createSaving.value = true
  pageError.value = ''
  try {
    const path = joinPath(directory.value.path, name)
    if (createKind.value === 'directory') {
      await api.createManagedDirectory(scope.value, path)
    } else {
      await api.createManagedTextFile(scope.value, path)
    }
    createOpen.value = false
    await load()
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    createSaving.value = false
  }
}

function selectFiles(event: Event): void {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files ?? [])
  input.value = ''
  if (!selected.length) return
  uploads.value = selected.map((file, index) => ({
    id: `${Date.now()}-${index}-${file.name}`,
    file,
    path: joinPath(directory.value.path, file.webkitRelativePath || file.name),
    progress: 0,
    status: 'pending',
    error: '',
  }))
  void runUploads()
}

async function runUploads(): Promise<void> {
  if (uploading.value) return
  uploading.value = true
  const selectedScope = scope.value
  let completed = 0
  for (const item of uploads.value) {
    item.status = 'uploading'
    try {
      await api.uploadManagedFile(selectedScope, item.path, item.file, false, (loaded, total) => {
        item.progress = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0
      })
      item.progress = 100
      item.status = 'completed'
      completed += 1
    } catch (error) {
      let failure: unknown = error
      let retry = false
      if (error instanceof ManagementApiError && error.code === 'file_already_exists') {
        retry = await confirmation.confirm({
          title: t('fileManager.overwrite.title'),
          description: t('fileManager.overwrite.description', { path: item.path }),
          confirmLabel: t('fileManager.overwrite.confirm'),
          cancelLabel: t('common.cancel'),
          dangerous: true,
        })
      }
      if (retry) {
        try {
          await api.uploadManagedFile(selectedScope, item.path, item.file, true, (loaded, total) => {
            item.progress = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0
          })
          item.progress = 100
          item.status = 'completed'
          completed += 1
          continue
        } catch (retryError) {
          failure = retryError
        }
      }
      item.status = 'failed'
      item.error = managementError.describe(failure).display
    }
  }
  uploading.value = false
  if (scope.value === selectedScope) await load()
  notify({
    tone: completed === uploads.value.length ? 'success' : 'danger',
    title: t('fileManager.upload.completed', { count: completed, total: uploads.value.length }),
  })
}

async function editText(item: ManagedFileItem): Promise<void> {
  const requestSequence = ++editorRequestSequence
  const requestedScope = scope.value
  editorOpen.value = true
  editorPath.value = item.path
  editorContent.value = ''
  editorRevision.value = ''
  editorError.value = ''
  editorLoading.value = true
  try {
    const response = await api.readManagedTextFile(requestedScope, item.path)
    if (!isCurrentEditorRequest(requestSequence, requestedScope, item.path)) return
    editorContent.value = response.content
    editorRevision.value = response.revision
  } catch (error) {
    if (!isCurrentEditorRequest(requestSequence, requestedScope, item.path)) return
    editorError.value = managementError.describe(error).display
  } finally {
    if (isCurrentEditorRequest(requestSequence, requestedScope, item.path)) editorLoading.value = false
  }
}

function closeEditor(): void {
  editorRequestSequence += 1
  editorOpen.value = false
  editorLoading.value = false
}

async function saveText(): Promise<void> {
  editorSaving.value = true
  editorError.value = ''
  try {
    const response = await api.saveManagedTextFile(
      scope.value,
      editorPath.value,
      editorContent.value,
      editorRevision.value,
    )
    editorRevision.value = response.revision
    notify({ tone: 'success', title: t('fileManager.editor.saved') })
    await load()
  } catch (error) {
    editorError.value = managementError.describe(error).display
  } finally {
    editorSaving.value = false
  }
}

function startRename(item: ManagedFileItem): void {
  renamingItem.value = item
  renameName.value = item.name
  renameOpen.value = true
}

async function renameItem(): Promise<void> {
  const name = renameName.value.trim()
  if (!renamingItem.value || !name) return
  renameSaving.value = true
  pageError.value = ''
  try {
    await api.renameManagedEntry(
      scope.value,
      renamingItem.value.path,
      name,
    )
    renameOpen.value = false
    await load()
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    renameSaving.value = false
  }
}

async function removeItem(item: ManagedFileItem): Promise<void> {
  const accepted = await confirmation.confirm({
    title: t('fileManager.delete.title'),
    description: t('fileManager.delete.description', { name: item.name }),
    confirmLabel: t('common.delete'),
    cancelLabel: t('common.cancel'),
    dangerous: true,
  })
  if (!accepted) return
  try {
    await api.deleteManagedFile(scope.value, item.path)
    await load()
  } catch (error) {
    pageError.value = managementError.describe(error).display
  }
}

async function download(item: ManagedFileItem): Promise<void> {
  if (item.kind === 'directory') {
    await downloadArchive([item])
    return
  }
  try {
    const blob = await api.downloadManagedEntry(scope.value, item.path)
    triggerBrowserDownload(blob, item.name)
  } catch (error) {
    pageError.value = managementError.describe(error).display
  }
}

function canSelect(item: ManagedFileItem): boolean {
  return item.kind !== 'unsupported'
}

function isSelected(item: ManagedFileItem): boolean {
  return selectedItems.value.some((selected) => selected.path === item.path)
}

function toggleSelection(item: ManagedFileItem, event: Event): void {
  const checked = (event.target as HTMLInputElement).checked
  selectedItems.value = checked
    ? [...selectedItems.value, item]
    : selectedItems.value.filter((selected) => selected.path !== item.path)
}

function toggleAll(event: Event): void {
  selectedItems.value = (event.target as HTMLInputElement).checked
    ? [...selectableItems.value]
    : []
}

async function downloadArchive(items: ManagedFileItem[]): Promise<void> {
  if (!items.length || archiveDownloading.value) return
  archiveDownloading.value = true
  pageError.value = ''
  const selectedScope = scope.value
  try {
    const paths = items.map((item) => item.path)
    const preview = await api.previewManagedArchive(selectedScope, paths)
    const accepted = await confirmation.confirm({
      title: t('fileManager.archive.confirmTitle'),
      description: t('fileManager.archive.confirmDescription', {
        fileCount: preview.file_count,
        directoryCount: preview.directory_count,
        size: formatSize(preview.total_size),
      }),
      confirmLabel: t('fileManager.archive.confirm'),
      cancelLabel: t('common.cancel'),
    })
    if (!accepted) return
    const blob = await api.downloadManagedArchive(selectedScope, paths)
    const filename = items.length === 1
      ? `${items[0]?.name ?? 'agent-shell-files'}.zip`
      : 'agent-shell-files.zip'
    triggerBrowserDownload(blob, filename)
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    archiveDownloading.value = false
  }
}

function formatSize(value: number | null): string {
  if (value === null) return '—'
  return new Intl.NumberFormat(formattingLocale(locale.value), {
    style: 'unit',
    unit: value >= 1024 * 1024 ? 'megabyte' : value >= 1024 ? 'kilobyte' : 'byte',
    unitDisplay: 'short',
    maximumFractionDigits: 1,
  }).format(value >= 1024 * 1024 ? value / (1024 * 1024) : value >= 1024 ? value / 1024 : value)
}

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(formattingLocale(locale.value), {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

onMounted(() => { void loadScopes() })
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton v-if="atManagerRoot" :disabled="loading" theme="info" type="button" @click="loadScopes">
        <span v-if="loading" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ t('common.refresh') }}
      </LteButton>
      <template v-else>
        <LteButton :disabled="uploading" theme="info" type="button" @click="load()">
          <span v-if="loading" class="spinner-border spinner-border-sm" aria-hidden="true" />
          {{ t('common.refresh') }}
        </LteButton>
        <LteButton :disabled="uploading" theme="success" type="button" @click="openCreate('directory')">
          {{ t('fileManager.createFolder') }}
        </LteButton>
        <LteButton :disabled="uploading" theme="success" type="button" @click="openCreate('file')">
          {{ t('fileManager.createFile') }}
        </LteButton>
        <LteButton :disabled="uploading" theme="success" type="button" @click="fileInput?.click()">
          {{ t('fileManager.uploadFiles') }}
        </LteButton>
        <LteButton :disabled="uploading" theme="success" type="button" @click="folderInput?.click()">
          {{ t('fileManager.uploadFolder') }}
        </LteButton>
        <LteButton
          :disabled="uploading || !selectedItems.length"
          theme="primary"
          type="button"
          @click="downloadArchive(selectedItems)"
        >
          <span v-if="archiveDownloading" class="spinner-border spinner-border-sm" aria-hidden="true" />
          {{ t('fileManager.archive.selected', { count: selectedItems.length }) }}
        </LteButton>
        <input ref="fileInput" class="d-none" multiple type="file" @change="selectFiles">
        <input ref="folderInput" class="d-none" multiple type="file" webkitdirectory @change="selectFiles">
      </template>
    </template>
    <template #status>
      <LteAlert
        v-if="pageError"
        data-testid="page-error"
        :title="t('fileManager.requestFailed')"
        theme="danger"
      >
        {{ pageError }}
      </LteAlert>
    </template>

    <LteCard>
      <template v-if="atManagerRoot">
        <div v-if="loading" class="d-flex align-items-center gap-2 p-3" aria-busy="true" role="status">
          <span class="spinner-border" aria-hidden="true" />
          <span>{{ t('common.loading') }}</span>
        </div>
        <div v-else class="table-responsive" data-testid="file-manager-roots">
          <table class="table table-hover align-middle">
            <thead class="management-table-head">
              <tr>
                <th>{{ t('fileManager.columns.name') }}</th>
                <th>{{ t('fileManager.columns.kind') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="scopes.length === 0">
                <td colspan="2" class="text-center text-body-secondary p-3">
                  {{ t('fileManager.emptyScopes') }}
                </td>
              </tr>
              <tr v-for="item in scopes" :key="item" :data-scope="item">
                <td>
                  <a href="#" class="d-flex align-items-center gap-2" @click.prevent="openScope(item)">
                    <i class="bi bi-folder" aria-hidden="true" />
                    {{ item }}
                  </a>
                </td>
                <td>{{ t('fileManager.kinds.directory') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-else>
        <nav :aria-label="t('fileManager.breadcrumb')" class="w-100 mb-3" data-testid="file-manager-breadcrumb">
          <ol class="breadcrumb flex-wrap mb-0">
            <li
              v-for="(item, index) in breadcrumbs"
              :key="`${item.path ?? 'manager-root'}:${index}`"
              class="breadcrumb-item"
              :aria-current="index === breadcrumbs.length - 1 ? 'page' : undefined"
            >
              <a
                v-if="index < breadcrumbs.length - 1"
                href="#"
                @click.prevent="navigateBreadcrumb(item.path)"
              >{{ item.label }}</a>
              <span v-else>{{ item.label }}</span>
            </li>
          </ol>
        </nav>

        <div v-if="loading" class="d-flex align-items-center gap-2 p-3" aria-busy="true" role="status">
          <span class="spinner-border" aria-hidden="true" />
          <span>{{ t('common.loading') }}</span>
        </div>
        <div v-else class="table-responsive">
        <table class="table table-hover align-middle">
          <thead class="management-table-head">
            <tr>
              <th>
                <input
                  :checked="allSelected"
                  class="form-check-input"
                  data-testid="select-all-files"
                  :disabled="selectableItems.length === 0"
                  :aria-label="t('fileManager.selectAll')"
                  type="checkbox"
                  @change="toggleAll"
                >
              </th>
              <th>{{ t('fileManager.columns.name') }}</th>
              <th>{{ t('fileManager.columns.kind') }}</th>
              <th>{{ t('fileManager.columns.size') }}</th>
              <th>{{ t('fileManager.columns.modified') }}</th>
              <th>{{ t('fileManager.columns.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="directory.items.length === 0">
              <td colspan="6" class="text-center text-body-secondary p-3">
                {{ t('fileManager.empty') }}
              </td>
            </tr>
            <tr v-for="row in directory.items" :key="row.path">
              <td>
                <input
                  v-if="canSelect(row)"
                  :checked="isSelected(row)"
                  class="form-check-input"
                  data-testid="select-file"
                  :aria-label="t('fileManager.selectItem', { name: row.name })"
                  type="checkbox"
                  @change="toggleSelection(row, $event)"
                >
              </td>
              <td>
                <a
                  v-if="row.kind === 'directory'"
                  class="font-monospace text-break"
                  data-testid="managed-entry-name"
                  href="#"
                  @click.prevent="load(row.path)"
                >
                  {{ row.name }}
                </a>
                <span v-else class="font-monospace text-break" data-testid="managed-entry-name">
                  {{ row.name }}
                </span>
              </td>
              <td>{{ t(`fileManager.kinds.${row.kind}`) }}</td>
              <td>{{ formatSize(row.size) }}</td>
              <td>{{ formatTime(row.modified_at) }}</td>
              <td>
                <div v-if="row.kind !== 'unsupported'" class="d-flex flex-wrap gap-1" data-testid="row-actions">
                  <LteButton v-if="row.kind === 'file'" size="sm" theme="warning" type="button" @click="editText(row)">
                    {{ t('common.edit') }}
                  </LteButton>
                  <LteButton size="sm" theme="info" type="button" @click="download(row)">
                    {{ t('fileManager.download') }}
                  </LteButton>
                  <LteButton size="sm" theme="warning" type="button" @click="startRename(row)">
                    {{ t('fileManager.rename') }}
                  </LteButton>
                  <LteButton size="sm" theme="danger" type="button" @click="removeItem(row)">
                    {{ t('common.delete') }}
                  </LteButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
      </template>
    </LteCard>

    <section v-if="!atManagerRoot && uploads.length" class="mt-3" aria-live="polite">
      <LteCard :title="t('fileManager.upload.title')">
        <div class="d-flex justify-content-end mb-3">
          <LteButton v-if="!uploading" size="sm" theme="warning" type="button" @click="uploads = []">
            {{ t('fileManager.upload.clear') }}
          </LteButton>
        </div>
        <div class="list-group list-group-flush">
        <div v-for="item in uploads" :key="item.id" class="list-group-item" data-testid="upload-item">
          <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
            <strong class="text-break">{{ item.path }}</strong>
            <span v-if="item.status === 'completed'" class="badge text-bg-success">
              {{ t('fileManager.upload.status.completed') }}
            </span>
            <span v-else-if="item.status === 'failed'" class="badge text-bg-danger">
              {{ t('fileManager.upload.status.failed') }}
            </span>
            <span v-else-if="item.status === 'uploading'" class="badge text-bg-info">
              {{ t('fileManager.upload.status.uploading') }}
            </span>
            <span v-else class="badge text-bg-secondary">
              {{ t('fileManager.upload.status.pending') }}
            </span>
          </div>
          <LteProgress v-if="item.status === 'completed'" :value="item.progress" show-label theme="success" />
          <LteProgress v-else-if="item.status === 'failed'" :value="item.progress" show-label theme="danger" />
          <LteProgress v-else :value="item.progress" show-label theme="primary" />
          <small v-if="item.error" class="d-block text-body-secondary text-break mt-2">{{ item.error }}</small>
        </div>
        </div>
      </LteCard>
    </section>

    <ModalHost
      :open="createOpen"
      :title="t(createKind === 'directory' ? 'fileManager.createFolder' : 'fileManager.createFile')"
      @close="createOpen = false"
    >
      <label class="form-label" for="create-entry-name">{{ t('fileManager.name') }}</label>
      <input
        id="create-entry-name"
        v-model="createName"
        autofocus
        class="form-control"
        @keyup.enter="createEntry"
      >
      <template #footer>
        <LteButton theme="warning" type="button" @click="createOpen = false">
          {{ t('common.cancel') }}
        </LteButton>
        <LteButton :disabled="!createName.trim()" theme="primary" type="button" @click="createEntry">
          <span v-if="createSaving" class="spinner-border spinner-border-sm" aria-hidden="true" />
          {{ t('common.new') }}
        </LteButton>
      </template>
    </ModalHost>

    <ModalHost
      :open="renameOpen"
      :title="t('fileManager.rename')"
      @close="renameOpen = false"
    >
      <label class="form-label" for="rename-entry-name">{{ t('fileManager.name') }}</label>
      <input
        id="rename-entry-name"
        v-model="renameName"
        class="form-control"
        @keyup.enter="renameItem"
      >
      <template #footer>
        <LteButton theme="warning" type="button" @click="renameOpen = false">
          {{ t('common.cancel') }}
        </LteButton>
        <LteButton :disabled="!renameName.trim()" theme="primary" type="button" @click="renameItem">
          <span v-if="renameSaving" class="spinner-border spinner-border-sm" aria-hidden="true" />
          {{ t('common.save') }}
        </LteButton>
      </template>
    </ModalHost>

    <ModalHost
      :open="editorOpen"
      size="wide"
      :title="editorPath"
      @close="closeEditor"
    >
      <div v-if="editorLoading" class="d-flex align-items-center gap-2 p-3" aria-busy="true" role="status">
        <span class="spinner-border" aria-hidden="true" />
        <span>{{ t('common.loading') }}</span>
      </div>
      <div v-else>
        <LteAlert v-if="editorError" class="mb-3" theme="danger">
          {{ editorError }}
        </LteAlert>
        <textarea v-model="editorContent" class="form-control" rows="18" spellcheck="false" />
      </div>
      <template #footer>
        <LteButton theme="warning" type="button" @click="editorOpen = false">
          {{ t('common.close') }}
        </LteButton>
        <LteButton :disabled="editorLoading || !editorRevision" theme="primary" type="button" @click="saveText">
          <span v-if="editorSaving" class="spinner-border spinner-border-sm" aria-hidden="true" />
          {{ t('common.save') }}
        </LteButton>
      </template>
    </ModalHost>
  </PageShell>
</template>
