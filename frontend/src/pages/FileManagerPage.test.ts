import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import type { FileManagerScope, ManagedDirectory } from '@/api'
import { useConfirmation } from '@/composables/useConfirmation'

import FileManagerPage from './FileManagerPage.vue'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return {
    ...actual,
    useI18n: () => ({
      locale: { value: 'en' },
      t: (key: string) => key,
      te: () => true,
    }),
  }
})

const fileScopeCatalog = {
  scopes: ['files', 'skills', 'python_templates'] as FileManagerScope[],
}

async function openFilesRoot(wrapper: ReturnType<typeof mount>): Promise<void> {
  await wrapper.get('[data-scope="files"] a').trigger('click')
  await flushPromises()
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((accept) => {
    resolve = accept
  })
  return { promise, resolve }
}

describe('FileManagerPage', () => {
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
    expect(wrapper.findAll('[data-testid="file-manager-roots"] tbody tr')).toHaveLength(3)
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
    expect(breadcrumb.text()).toContain('files')
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

  it('keeps the latest directory when an earlier breadcrumb request finishes late', async () => {
    const staleDirectory = deferred<ManagedDirectory>()
    const latestDirectory = deferred<ManagedDirectory>()
    const initialDirectory: ManagedDirectory = {
      scope: 'files',
      path: 'one/two',
      items: [],
    }
    const listManagedFiles = vi.fn()
      .mockResolvedValueOnce(initialDirectory)
      .mockImplementation((_: FileManagerScope, path: string) => (
        path === 'one' ? staleDirectory.promise : latestDirectory.promise
      ))
    const api = {
      listManagedFileScopes: vi.fn().mockResolvedValue(fileScopeCatalog),
      listManagedFiles,
      createManagedDirectory: vi.fn(),
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
    await openFilesRoot(wrapper)

    const breadcrumbLinks = wrapper.get('[data-testid="file-manager-breadcrumb"]').findAll('a')
    await breadcrumbLinks[2]!.trigger('click')
    await breadcrumbLinks[1]!.trigger('click')
    latestDirectory.resolve({
      scope: 'files',
      path: '',
      items: [{
        name: 'latest.txt',
        path: 'latest.txt',
        kind: 'file',
        size: 6,
        modified_at: '2026-08-03T00:00:00Z',
        revision: 'latest-revision',
      }],
    })
    await flushPromises()
    staleDirectory.resolve({
      scope: 'files',
      path: 'one',
      items: [{
        name: 'stale.txt',
        path: 'one/stale.txt',
        kind: 'file',
        size: 5,
        modified_at: '2026-08-02T00:00:00Z',
        revision: 'stale-revision',
      }],
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="file-manager-breadcrumb"]').text()).not.toContain('one')
    expect(wrapper.get('[data-testid="managed-entry-name"]').text()).toBe('latest.txt')
  })

  it('keeps the latest editor content when an earlier text request finishes late', async () => {
    const firstText = deferred<{ content: string, revision: string }>()
    const secondText = deferred<{ content: string, revision: string }>()
    const directory: ManagedDirectory = {
      scope: 'files',
      path: '',
      items: [
        {
          name: 'first.txt',
          path: 'first.txt',
          kind: 'file',
          size: 5,
          modified_at: '2026-08-02T00:00:00Z',
          revision: 'first-list-revision',
        },
        {
          name: 'second.txt',
          path: 'second.txt',
          kind: 'file',
          size: 6,
          modified_at: '2026-08-03T00:00:00Z',
          revision: 'second-list-revision',
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
      previewManagedArchive: vi.fn(),
      downloadManagedArchive: vi.fn(),
      readManagedTextFile: vi.fn((_: FileManagerScope, path: string) => (
        path === 'first.txt' ? firstText.promise : secondText.promise
      )),
      saveManagedTextFile: vi.fn(),
      renameManagedEntry: vi.fn(),
      deleteManagedFile: vi.fn(),
    }
    const wrapper = mount(FileManagerPage, { props: { api } })
    await flushPromises()
    await openFilesRoot(wrapper)

    const rowActions = wrapper.findAll('[data-testid="row-actions"]')
    await rowActions[0]!.findAll('button')[0]!.trigger('click')
    await rowActions[1]!.findAll('button')[0]!.trigger('click')
    secondText.resolve({ content: 'latest content', revision: 'latest-revision' })
    await flushPromises()
    firstText.resolve({ content: 'stale content', revision: 'stale-revision' })
    await flushPromises()

    expect(wrapper.get('[role="dialog"]').text()).toContain('second.txt')
    expect((wrapper.get('[role="dialog"] textarea').element as HTMLTextAreaElement).value)
      .toBe('latest content')
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
