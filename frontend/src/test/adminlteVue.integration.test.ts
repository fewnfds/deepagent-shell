import { mount } from '@vue/test-utils'
import {
  LteInput,
  LteInputFile,
  LteModal,
  LteSelect,
  LteSidebarNav,
  LteToast,
  provideColorMode,
  type MenuNode,
} from '@adminlte/vue'
import { defineComponent, nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const storage = new Map<string, string>()
const storageMock = {
  clear: () => storage.clear(),
  getItem: (key: string) => storage.get(key) ?? null,
  key: (index: number) => [...storage.keys()][index] ?? null,
  get length() {
    return storage.size
  },
  removeItem: (key: string) => storage.delete(key),
  setItem: (key: string, value: string) => storage.set(key, String(value)),
}

beforeEach(() => {
  storage.clear()
  vi.stubGlobal('localStorage', storageMock)
})

afterEach(() => {
  document.body.innerHTML = ''
  document.documentElement.removeAttribute('data-bs-theme')
  storage.clear()
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('@adminlte/vue 0.3.0 integration boundary', () => {
  it('emits strings from number inputs so product code must convert explicitly', async () => {
    const wrapper = mount(LteInput, {
      props: { modelValue: 7, type: 'number' },
    })

    await wrapper.get('input').setValue('12')

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['12'])
  })

  it('emits strings from numeric select options so numeric selects remain controlled', async () => {
    const wrapper = mount(LteSelect, {
      props: {
        modelValue: 1,
        options: [
          { value: 1, label: 'One' },
          { value: 2, label: 'Two' },
        ],
      },
    })

    await wrapper.get('select').setValue('2')

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['2'])
  })

  it('passes paths to RouterLink and marks the matching sidebar item active', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/settings', component: { template: '<div />' } },
      ],
    })
    await router.push('/settings')
    await router.isReady()
    const items: MenuNode[] = [
      { type: 'item', text: 'Home', href: '/' },
      { type: 'item', text: 'Settings', href: '/settings' },
    ]

    const wrapper = mount(LteSidebarNav, {
      props: {
        currentPath: router.currentRoute.value.path,
        items,
        linkComponent: 'RouterLink',
      },
      global: {
        plugins: [router],
      },
    })

    const settingsLink = wrapper.get('a[href="/settings"]')
    expect(settingsLink.classes()).toContain('active')
    expect(settingsLink.attributes('aria-current')).toBe('page')
  })

  it('returns the selected FileList without reading file contents', async () => {
    const wrapper = mount(LteInputFile, { props: { modelValue: null } })
    const input = wrapper.get<HTMLInputElement>('input[type="file"]')
    const file = new File(['content'], 'sample.txt', { type: 'text/plain' })
    const files = {
      0: file,
      length: 1,
      item: (index: number) => index === 0 ? file : null,
    } as unknown as FileList
    Object.defineProperty(input.element, 'files', { configurable: true, value: files })

    await input.trigger('change')

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([files])
  })

  it('applies and persists light, dark, and auto modes through the official composable', async () => {
    const media = {
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal('matchMedia', vi.fn(() => media))
    const ThemeHarness = defineComponent({
      setup() {
        return provideColorMode({ initialMode: 'auto' })
      },
      template: '<button type="button" @click="setColorMode(\'dark\')">Dark</button>',
    })
    const wrapper = mount(ThemeHarness)
    await nextTick()

    expect(document.documentElement.getAttribute('data-bs-theme')).toBe('light')
    await wrapper.get('button').trigger('click')
    await nextTick()

    expect(document.documentElement.getAttribute('data-bs-theme')).toBe('dark')
    expect(localStorage.getItem('lte-theme')).toBe('dark')
  })

  it('closes modal on Escape and returns focus to the opener', async () => {
    vi.useFakeTimers()
    const ModalHarness = defineComponent({
      components: { LteModal },
      setup() {
        return { open: ref(false) }
      },
      template: `
        <button id="opener" type="button" @click="open = true">Open</button>
        <LteModal v-model="open" title="Dialog">
          <input id="modal-input" aria-label="Modal input">
          <button type="button">Last action</button>
        </LteModal>
      `,
    })
    const wrapper = mount(ModalHarness, {
      attachTo: document.body,
      global: { stubs: { Teleport: false, Transition: false } },
    })
    const opener = wrapper.get<HTMLButtonElement>('#opener')
    opener.element.focus()

    await opener.trigger('click')
    await nextTick()
    await nextTick()
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')
    expect(dialog).not.toBeNull()
    expect(dialog?.contains(document.activeElement)).toBe(true)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    vi.runAllTimers()
    await nextTick()

    expect(wrapper.vm.open).toBe(false)
    expect(document.activeElement).toBe(opener.element)
    wrapper.unmount()
  })

  it('documents that an initially open modal skips its focus and Escape setup', async () => {
    const wrapper = mount(LteModal, {
      attachTo: document.body,
      props: { modelValue: true, title: 'Initially open dialog' },
      global: { stubs: { Teleport: false, Transition: false } },
    })
    await nextTick()

    expect(document.body.classList.contains('modal-open')).toBe(false)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })

  it('autohides toast after it changes from closed to open', async () => {
    vi.useFakeTimers()
    const ToastHarness = defineComponent({
      components: { LteToast },
      setup() {
        return { open: ref(false) }
      },
      template: `
        <button type="button" @click="open = true">Show</button>
        <LteToast v-model="open" title="Status" :delay="1000">Saved</LteToast>
      `,
    })
    const wrapper = mount(ToastHarness)

    await wrapper.get('button').trigger('click')
    await nextTick()
    expect(wrapper.get('[role="alert"]').classes()).toContain('show')

    vi.advanceTimersByTime(1000)
    await nextTick()

    expect(wrapper.vm.open).toBe(false)
  })

  it('documents that an initially open toast does not start its autohide timer', async () => {
    vi.useFakeTimers()
    const wrapper = mount(LteToast, {
      props: {
        autohide: true,
        delay: 1000,
        modelValue: true,
        title: 'Initially open toast',
      },
    })

    vi.advanceTimersByTime(1000)
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.get('[role="alert"]').classes()).toContain('show')
  })
})
