import { createI18n } from 'vue-i18n'

import { readBrowserStorage, writeBrowserStorage } from '@/browserStorage'

import { en } from './en'
import { type MessageSchema, zhCN } from './zh-CN'

export type SupportedLocale = 'zh-CN' | 'en'

export function messageKeys(value: object, prefix = ''): string[] {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return child && typeof child === 'object' ? messageKeys(child as object, path) : [path]
  }).sort()
}

export function messageValues(value: object): string[] {
  return Object.values(value).flatMap((child) => child && typeof child === 'object'
    ? messageValues(child as object)
    : [String(child)])
}

export function assertLocaleParity(): void {
  const source = messageKeys(zhCN)
  const target = messageKeys(en)
  if (source.join('\n') !== target.join('\n')) {
    throw new Error('Locale message keys are not identical for zh-CN and en.')
  }
  if ([...messageValues(zhCN), ...messageValues(en)].some((value) => value.trim() === '')) {
    throw new Error('Locale messages must not be empty.')
  }
}

export function resolveInitialLocale(saved: string | null, browserLanguages: readonly string[]): SupportedLocale {
  if (saved === 'zh-CN' || saved === 'en') return saved
  return browserLanguages.some((value) => value.toLowerCase().startsWith('zh')) ? 'zh-CN' : 'en'
}

function readSavedLocale(): string | null {
  return readBrowserStorage('agent-shell-locale')
}

assertLocaleParity()

const locale = resolveInitialLocale(
  readSavedLocale(),
  window.navigator.languages,
)
window.document.documentElement.lang = locale

export const i18n = createI18n<[MessageSchema], SupportedLocale>({
  legacy: false,
  globalInjection: true,
  locale,
  fallbackLocale: false,
  missingWarn: true,
  fallbackWarn: false,
  messages: {
    'zh-CN': zhCN,
    en,
  },
})

export function setLocale(value: SupportedLocale): void {
  i18n.global.locale.value = value
  writeBrowserStorage('agent-shell-locale', value)
  window.document.documentElement.lang = value
}
