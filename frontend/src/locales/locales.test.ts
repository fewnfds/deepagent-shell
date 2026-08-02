import { describe, expect, it } from 'vitest'

import { en } from './en'
import { assertLocaleParity, messageKeys, messageValues, resolveInitialLocale } from './index'
import { zhCN } from './zh-CN'

describe('locale contract', () => {
  it('keeps zh-CN and en keys identical', () => {
    expect(() => assertLocaleParity()).not.toThrow()
    expect(messageKeys(zhCN)).toEqual(messageKeys(en))
    expect(messageValues(zhCN).every((value) => value.trim().length > 0)).toBe(true)
    expect(messageValues(en).every((value) => value.trim().length > 0)).toBe(true)
  })

  it('uses a saved locale before browser language', () => {
    expect(resolveInitialLocale('en', ['zh-CN'])).toBe('en')
    expect(resolveInitialLocale(null, ['zh-Hans', 'en'])).toBe('zh-CN')
    expect(resolveInitialLocale(null, ['fr'])).toBe('en')
  })
})
