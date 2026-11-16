// Carátulas: Python ya filtra las URL, pero la interfaz no se fía de nada que vaya a un <img>.

const COVER_HOST = /^[a-z0-9-]+(\.[a-z0-9-]+)*\.mzstatic\.com$/

/** Devuelve la URL si es una imagen de la CDN de Apple por https (o un data: de imagen). */
export function safeCoverUrl(url: string | null | undefined): string | null {
  if (!url) return null
  if (/^data:image\/(png|jpeg|webp|svg\+xml)[;,]/.test(url)) return url
  try {
    const u = new URL(url)
    if (u.protocol !== 'https:' || u.username || u.password || u.port) return null
    return COVER_HOST.test(u.hostname) ? u.href : null
  } catch {
    return null
  }
}

/** Tono estable (0–360) a partir del nombre, para el marcador de posición sin carátula. */
export function hueFor(text: string): number {
  let h = 0
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0
  return 180 + (h % 80) // familia fría: cian → azul → violeta
}
