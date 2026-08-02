import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import type {
  ApiServerSettings,
  ApiServerSettingsUpdate,
  FileManagerScope,
  ManagedDirectory,
  SystemSettings,
  SystemSettingsUpdate,
} from '@/api'
import { useConfirmation } from '@/composables/useConfirmation'

import FileManagerPage from './FileManagerPage.vue'
import SystemSettingsPage from './SystemSettingsPage.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    locale: { value: 'en' },
    t: (key: string) => key,
  }),
}))

const currentSettings: SystemSettings = {
  host: '127.0.0.1',
  port: 19100,
  allow_remote: false,
  management_token: { configured: true },
  cors_origins: [],
  trusted_proxy_cidrs: [],
  restart_required: false,
  active_management_url: 'http://127.0.0.1:19100/admin',
}

const currentApiServerSettings: ApiServerSettings = {
  enabled: false,
  status: 'stopped',
  api_key: { configured: true },
  max_initial_messages: 1000,
  api_base_url: 'http://127.0.0.1:19100/v1',
  models_endpoint: 'http://127.0.0.1:19100/v1/models',
  chat_completions_endpoint: 'http://127.0.0.1:19100/v1/chat/completions',
  runtime: 'model_streaming',
}

const fileScopeCatalog = {
  scopes: ['files', 'skills', 'custom_tools', 'custom_middlewares'] as FileManagerScope[],
}

async function openFilesRoot(wrapper: ReturnType<typeof mount>): Promise<void> {
  await wrapper.get('[data-scope="files"] a').trigger('click')
  await flushPromises()
}

describe('system pages', () => {
  it('loads and saves typed system settings without filling secret values', async () => {
    const api = {
      getSystemSettings: vi.fn().mockResolvedValue(currentSettings),
      getApiServer: vi.fn().mockResolvedValue(currentApiServerSettings),
      getInterceptionTest: vi.fn().mockResolvedValue({ enabled: false }),
      updateSystemSettings: vi.fn().mockResolvedValue({
        ...currentSettings,
        restart_required: true,
      }),
      saveApiServer: vi.fn().mockResolvedValue(currentApiServerSettings),
      updateInterceptionTest: vi.fn(async (enabled: boolean) => ({ enabled })),
    }
    const wrapper = mount(SystemSettingsPage, { props: { api } })
    await flushPromises()

    const cards = wrapper.findAll('[data-testid^="system-card-"]')
    expect(cards).toHaveLength(4)
    expect(cards.every((card) => !card.classes().includes('card-primary'))).toBe(true)
    expect(cards.map((card) => card.get('.card-header i').classes().find((name) => name.startsWith('bi-'))))
      .toEqual(['bi-hdd-network', 'bi-key', 'bi-sliders', 'bi-shield-lock'])
    expect(cards.every((card) => card.get('.card-title').element.tagName === 'H2')).toBe(true)

    const saveButtons = wrapper.findAll('button').filter((button) => button.text() === 'common.save')
    expect(saveButtons).toHaveLength(1)
    await saveButtons[0]!.trigger('click')
    await flushPromises()

    expect(api.updateSystemSettings).toHaveBeenCalledWith({
      host: '127.0.0.1',
      port: 19100,
      allow_remote: false,
      management_token: { operation: 'preserve' },
      cors_origins: [],
      trusted_proxy_cidrs: [],
    })
    expect(api.saveApiServer).toHaveBeenCalledWith({
      api_key: { operation: 'keep' },
      max_initial_messages: 1000,
    })
    expect(api.updateInterceptionTest).toHaveBeenCalledWith(false)
    expect(wrapper.text()).toContain('systemSettings.restartRequired')
    expect(wrapper.text()).not.toContain('test-management-token')
  })

  it('converts edited number, switch, secret and multiline fields into the backend payload', async () => {
    const api = {
      getSystemSettings: vi.fn().mockResolvedValue(currentSettings),
      getApiServer: vi.fn().mockResolvedValue(currentApiServerSettings),
      getInterceptionTest: vi.fn().mockResolvedValue({ enabled: false }),
      updateSystemSettings: vi.fn().mockImplementation(async (payload: SystemSettingsUpdate) => ({
        ...currentSettings,
        host: payload.host,
        port: payload.port,
        allow_remote: payload.allow_remote,
        cors_origins: payload.cors_origins,
        trusted_proxy_cidrs: payload.trusted_proxy_cidrs,
      })),
      saveApiServer: vi.fn().mockImplementation(async (payload: ApiServerSettingsUpdate) => ({
        ...currentApiServerSettings,
        max_initial_messages: payload.max_initial_messages ?? 1000,
      })),
      updateInterceptionTest: vi.fn(async (enabled: boolean) => ({ enabled })),
    }
    const wrapper = mount(SystemSettingsPage, { props: { api } })
    await flushPromises()

    await wrapper.get('input[type="text"]').setValue('0.0.0.0')
    await wrapper.get('#system-port').setValue('21000')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('#management-password').setValue('new-management-password')
    await wrapper.get('#api-server-key').setValue('new-api-key')
    await wrapper.get('#max-initial-messages').setValue('2500')
    await wrapper.get('#interception-test').setValue(true)
    const textareas = wrapper.findAll('textarea')
    await textareas[0]!.setValue('http://localhost:3000\nhttp://127.0.0.1:3000')
    await textareas[1]!.setValue('127.0.0.1/32')
    const save = wrapper.findAll('button').find((button) => button.text() === 'common.save')
    await save!.trigger('click')
    await flushPromises()

    expect(api.updateSystemSettings).toHaveBeenCalledWith({
      host: '0.0.0.0',
      port: 21000,
      allow_remote: true,
      management_token: { operation: 'replace', value: 'new-management-password' },
      cors_origins: ['http://localhost:3000', 'http://127.0.0.1:3000'],
      trusted_proxy_cidrs: ['127.0.0.1/32'],
    })
    expect(api.saveApiServer).toHaveBeenCalledWith({
      api_key: { operation: 'replace', value: 'new-api-key' },
      max_initial_messages: 2500,
    })
    expect(api.updateInterceptionTest).toHaveBeenCalledWith(true)
  })

  it('reveals only newly entered credentials and clears an edited API key through the unified save', async () => {
    const api = {
      getSystemSettings: vi.fn().mockResolvedValue(currentSettings),
      getApiServer: vi.fn().mockResolvedValue(currentApiServerSettings),
      getInterceptionTest: vi.fn().mockResolvedValue({ enabled: false }),
      updateSystemSettings: vi.fn().mockResolvedValue(currentSettings),
      saveApiServer: vi.fn().mockResolvedValue({
        ...currentApiServerSettings,
        api_key: { configured: false },
      }),
      updateInterceptionTest: vi.fn(async (enabled: boolean) => ({ enabled })),
    }
    const wrapper = mount(SystemSettingsPage, { props: { api } })
    await flushPromises()

    const managementPassword = wrapper.get('#management-password')
    const apiKey = wrapper.get('#api-server-key')
    expect(managementPassword.attributes('type')).toBe('password')
    expect(apiKey.attributes('type')).toBe('password')
    await managementPassword.setValue('visible-management-password')
    await managementPassword.element.parentElement!.querySelector('button')!.click()
    await apiKey.setValue('temporary-key')
    await apiKey.element.parentElement!.querySelector('button')!.click()
    expect(managementPassword.attributes('type')).toBe('text')
    expect(apiKey.attributes('type')).toBe('text')

    await apiKey.setValue('')
    await wrapper.get('[data-testid="system-settings-form"]').trigger('submit')
    await flushPromises()

    expect(api.saveApiServer).toHaveBeenCalledWith({
      api_key: { operation: 'clear' },
      max_initial_messages: 1000,
    })
  })

  it('lists only backend-authorized file roots and creates a folder after entering one', async () => {
    const empty: ManagedDirectory = { scope: 'files', path: '', items: [] }
    const api = {
      listManagedFileScopes: vi.fn().mockResolvedValue(fileScopeCatalog),
      listManagedFiles: vi.fn().mockResolvedValue(empty),
      createManagedDirectory: vi.fn().mockResolvedValue({ path: 'drafts' }),
      createManagedTextFile: vi.fn(),
      uploadManagedFile: vi.fn(),
      downloadManagedEntry: vi.fn(),
      previewManagedArchive: vi.fn(),
      downloadManagedArchive: vi.fn(),
      readManagedTextFile: vi.fn(),
      saveManagedTextFile: vi.fn(),
      renameManagedEntry: vi.fn(),
      deleteManagedFile: vi.fn(),
    }
    const wrapper = mount(FileManagerPage, { props: { api } })
    await flushPromises()

    expect(wrapper.find('#file-manager-scope').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="file-manager-roots"] tbody tr')).toHaveLength(4)
    expect(wrapper.find('[data-scope="config"]').exists()).toBe(false)
    expect(api.listManagedFiles).not.toHaveBeenCalled()

    await openFilesRoot(wrapper)
    expect(api.listManagedFiles).toHaveBeenCalledWith('files', '')

    const createFolder = wrapper.findAll('button').find((button) => (
      button.text() === 'fileManager.createFolder'
    ))
    await createFolder!.trigger('click')
    await flushPromises()
    const dialogInput = wrapper.find('[role="dialog"] input')
    await dialogInput.setValue('drafts')
    const create = wrapper.findAll('[role="dialog"] button').find((button) => (
      button.text() === 'common.new'
    ))
    await create!.trigger('click')
    await flushPromises()

    expect(api.createManagedDirectory).toHaveBeenCalledWith('files', 'drafts')
    expect(api.listManagedFiles).toHaveBeenCalledTimes(2)
  })

  it('keeps file actions distinct and renames within the current folder', async () => {
    const directory: ManagedDirectory = {
      scope: 'files',
      path: 'notes',
      items: [{
        name: 'draft.txt',
        path: 'notes/draft.txt',
        kind: 'file',
        size: 5,
        modified_at: '2026-07-21T00:00:00Z',
        revision: 'revision',
      }],
    }
    const api = {
      listManagedFileScopes: vi.fn().mockResolvedValue(fileScopeCatalog),
      listManagedFiles: vi.fn().mockResolvedValue(directory),
      createManagedDirectory: vi.fn(),
      createManagedTextFile: vi.fn(),
      uploadManagedFile: vi.fn(),
      downloadManagedEntry: vi.fn(),
      previewManagedArchive: vi.fn(),
      downloadManagedArchive: vi.fn(),
      readManagedTextFile: vi.fn(),
      saveManagedTextFile: vi.fn(),
      renameManagedEntry: vi.fn().mockResolvedValue({ path: 'notes/final.txt' }),
      deleteManagedFile: vi.fn(),
    }
    const wrapper = mount(FileManagerPage, { props: { api } })
    await flushPromises()
    await openFilesRoot(wrapper)

    const breadcrumb = wrapper.get('[data-testid="file-manager-breadcrumb"]')
    expect(breadcrumb.text()).toContain('fileManager.title')
    expect(breadcrumb.text()).toContain('fileManager.scopes.files')
    expect(breadcrumb.text()).toContain('notes')
    expect(breadcrumb.findAll('button')).toHaveLength(0)
    expect(breadcrumb.findAll('a')).toHaveLength(2)

    const fileName = wrapper.get('[data-testid="managed-entry-name"]')
    expect(fileName.element.tagName).toBe('SPAN')
    expect(fileName.text()).toBe('draft.txt')

    const actions = wrapper.findAll('[data-testid="row-actions"] button')
    expect(actions.map((button) => button.text())).toEqual([
      'common.edit',
      'fileManager.download',
      'fileManager.rename',
      'common.delete',
    ])
    expect(actions[0]?.classes()).toContain('btn-warning')
    expect(actions[1]?.classes()).toContain('btn-info')
    expect(actions[2]?.classes()).toContain('btn-warning')
    expect(actions[3]?.classes()).toContain('btn-danger')

    await actions[2]!.trigger('click')
    await wrapper.get('[role="dialog"] input').setValue('final.txt')
    const save = wrapper.findAll('[role="dialog"] button').find((button) => (
      button.text() === 'common.save'
    ))
    await save!.trigger('click')
    await flushPromises()

    expect(api.renameManagedEntry).toHaveBeenCalledWith(
      'files',
      'notes/draft.txt',
      'final.txt',
    )
  })

  it('previews mixed selections and creates the archive only after confirmation', async () => {
    const directory: ManagedDirectory = {
      scope: 'files',
      path: '',
      items: [
        {
          name: 'documents',
          path: 'documents',
          kind: 'directory',
          size: null,
          modified_at: '2026-07-21T00:00:00Z',
          revision: 'directory-revision',
        },
        {
          name: 'readme.txt',
          path: 'readme.txt',
          kind: 'file',
          size: 4,
          modified_at: '2026-07-21T00:00:00Z',
          revision: 'file-revision',
        },
      ],
    }
    const api = {
      listManagedFileScopes: vi.fn().mockResolvedValue(fileScopeCatalog),
      listManagedFiles: vi.fn().mockResolvedValue(directory),
      createManagedDirectory: vi.fn(),
      createManagedTextFile: vi.fn(),
      uploadManagedFile: vi.fn(),
      downloadManagedEntry: vi.fn(),
      previewManagedArchive: vi.fn().mockResolvedValue({
        total_size: 1028,
        file_count: 2,
        directory_count: 1,
      }),
      downloadManagedArchive: vi.fn().mockResolvedValue(new Blob(['archive'])),
      readManagedTextFile: vi.fn(),
      saveManagedTextFile: vi.fn(),
      renameManagedEntry: vi.fn(),
      deleteManagedFile: vi.fn(),
    }
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:archive'),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = mount(FileManagerPage, { props: { api } })
    await flushPromises()
    await openFilesRoot(wrapper)

    await wrapper.get('[data-testid="select-all-files"]').setValue(true)
    await flushPromises()
    const archive = wrapper.findAll('button').find((button) => (
      button.text() === 'fileManager.archive.selected'
    ))
    expect(archive).toBeDefined()
    expect(archive!.attributes('disabled')).toBeUndefined()

    await archive!.trigger('click')
    await flushPromises()
    expect(api.previewManagedArchive).toHaveBeenCalledWith(
      'files',
      ['documents', 'readme.txt'],
    )
    expect(api.downloadManagedArchive).not.toHaveBeenCalled()

    useConfirmation().cancel()
    await flushPromises()
    expect(api.downloadManagedArchive).not.toHaveBeenCalled()

    await archive!.trigger('click')
    await flushPromises()
    useConfirmation().accept()
    await flushPromises()
    expect(api.downloadManagedArchive).toHaveBeenCalledWith(
      'files',
      ['documents', 'readme.txt'],
    )
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:archive')
  })
})
