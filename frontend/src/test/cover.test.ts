import { describe, expect, it } from 'vitest'

import { hueFor, safeCoverUrl, safePreviewUrl } from '../lib/cover'

describe('safeCoverUrl', () => {
  it('acepta la CDN de Apple por https', () => {
    const url = 'https://is1-ssl.mzstatic.com/image/thumb/x/600x600bb.jpg'
    expect(safeCoverUrl(url)).toBe(url)
  })

  it.each([
    null,
    undefined,
    '',
    'http://is1-ssl.mzstatic.com/a.jpg',
    'https://evil.example.com/a.jpg',
    'https://mzstatic.com.evil.example/a.jpg',
    'https://user@is1-ssl.mzstatic.com/a.jpg',
    'https://is1-ssl.mzstatic.com:444/a.jpg',
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
  ])('rechaza %s', (url) => {
    expect(safeCoverUrl(url)).toBeNull()
  })

  it('acepta imágenes data: (modo demo)', () => {
    expect(safeCoverUrl('data:image/svg+xml;utf8,%3Csvg%3E')).not.toBeNull()
  })
})

describe('safePreviewUrl', () => {
  const preview =
    'https://audio-ssl.itunes.apple.com/itunes-assets/AudioPreview211/v4/mzaf_1.plus.aac.p.m4a'

  it('acepta las preescuchas de Apple por https y quita la query', () => {
    expect(safePreviewUrl(preview)).toBe(preview)
    expect(safePreviewUrl(`${preview}?x=1#y`)).toBe(preview)
  })

  it.each([
    null,
    'http://audio-ssl.itunes.apple.com/a.m4a',
    'https://evil.example.com/a.m4a',
    'https://itunes.apple.com.evil.example/a.m4a',
    'https://audio-ssl.itunes.apple.com/a.exe',
    'https://user@audio-ssl.itunes.apple.com/a.m4a',
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
  ])('rechaza %s', (url) => {
    expect(safePreviewUrl(url)).toBeNull()
  })
})

describe('hueFor', () => {
  it('es estable y frío', () => {
    expect(hueFor('a|b')).toBe(hueFor('a|b'))
    const h = hueFor('Joey Harmless|Ready')
    expect(h).toBeGreaterThanOrEqual(180)
    expect(h).toBeLessThan(260)
  })
})
