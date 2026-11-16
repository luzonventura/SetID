import { describe, expect, it } from 'vitest'

import { hueFor, safeCoverUrl } from '../lib/cover'

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

describe('hueFor', () => {
  it('es estable y frío', () => {
    expect(hueFor('a|b')).toBe(hueFor('a|b'))
    const h = hueFor('Joey Harmless|Ready')
    expect(h).toBeGreaterThanOrEqual(180)
    expect(h).toBeLessThan(260)
  })
})
