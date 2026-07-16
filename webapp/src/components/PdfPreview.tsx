import * as pdfjs from 'pdfjs-dist'
import { TextLayer } from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import { ChevronDown, ChevronUp, ZoomIn, ZoomOut } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { t } from '../i18n'
import './pdfpreview.css'

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

export interface Highlight {
  page?: number | null
  rawText?: string | null
  location?: string | null
}

const MIN_ZOOM = 0.5
const MAX_ZOOM = 3
const ZOOM_STEP = 0.25

// NFKC folds full-width/ligature variants so CJK and OCR text compare cleanly.
const norm = (s: string) => s.normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase()

interface SpanEntry {
  span: HTMLElement
  text: string
}

/** One contiguous match of a target in a page's text layer: the spans it
 * covers plus the index of the first covered entry (reading-order anchor,
 * comparable across matching passes). */
interface Occurrence {
  spans: HTMLElement[]
  anchor: number
}

function collectEntries(pageDiv: HTMLElement): SpanEntry[] {
  const entries: SpanEntry[] = []
  for (const span of pageDiv.querySelectorAll<HTMLElement>('.textLayer span')) {
    const text = norm(span.textContent ?? '')
    if (text) entries.push({ span, text })
  }
  return entries
}

// Progressively looser passes: exact spacing → spacing-insensitive →
// letters/digits/decimal point only (survives punctuation drift like
// "1,234.56" vs "1 234.56"). The decimal point stays significant even in the
// loosest pass; without it a short numeric target like "2.04" collapses onto
// any "20.4" on the page.
const passes = [
  { clean: (s: string) => s, sep: ' ' },
  { clean: (s: string) => s.replace(/ /g, ''), sep: '' },
  { clean: (s: string) => s.replace(/[^\p{L}\p{N}.]+/gu, ''), sep: '' },
]

/** Finds the target as a CONTIGUOUS run in the page's text layer and returns
 * every place it occurs (strictest matching pass that hits anything wins).
 * Matching per-span substrings instead lights up every fragment that happens
 * to occur in the target (dates, short numbers), which scatters false
 * highlights across the page. */
function findOccurrences(entries: SpanEntry[], target: string): Occurrence[] {
  for (const { clean, sep } of passes) {
    const needle = clean(target)
    if (needle.length < 3) continue
    let joined = ''
    const ranges: { start: number; end: number; span: HTMLElement; entry: number }[] = []
    entries.forEach(({ span, text }, entry) => {
      const piece = clean(text)
      if (!piece) return
      if (joined) joined += sep
      ranges.push({ start: joined.length, end: joined.length + piece.length, span, entry })
      joined += piece
    })
    const occurrences: Occurrence[] = []
    for (let from = 0; ; ) {
      const idx = joined.indexOf(needle, from)
      if (idx === -1) break
      const end = idx + needle.length
      const hit = ranges.filter((r) => r.start < end && r.end > idx)
      if (hit.length > 0) occurrences.push({ spans: hit.map((r) => r.span), anchor: hit[0].entry })
      from = end
    }
    if (occurrences.length > 0) return occurrences
  }
  return []
}

/** Data-dense pages repeat short values ("2.04" in a table AND a chart
 * legend), so when the target occurs more than once, pick the occurrence
 * closest in reading order to the extraction's location label. */
function pickOccurrence(
  entries: SpanEntry[],
  occurrences: Occurrence[],
  location: string | null | undefined,
): Occurrence {
  if (occurrences.length === 1 || !location) return occurrences[0]
  const anchors = findOccurrences(entries, norm(location)).map((o) => o.anchor)
  if (anchors.length === 0) {
    // The location is model-written prose and may not appear verbatim;
    // fall back to anchoring on its individual words.
    for (const token of norm(location).split(' ')) {
      if (token.length < 4) continue
      anchors.push(...findOccurrences(entries, token).map((o) => o.anchor))
    }
  }
  if (anchors.length === 0) return occurrences[0]
  const dist = (o: Occurrence) => Math.min(...anchors.map((a) => Math.abs(o.anchor - a)))
  return occurrences.reduce((best, o) => (dist(o) < dist(best) ? o : best))
}

interface Props {
  file: File
  highlight: Highlight | null
}

/** Renders a PDF (all pages) or an image, with text-layer highlighting and a
 * page/zoom toolbar. Highlighting matches the extraction's raw_text against
 * the source page's text layer, falling back to the other pages when the
 * reported page is off; scanned PDFs (no text layer) degrade to page scroll +
 * the location banner shown by the parent. */
export default function PdfPreview({ file, highlight }: Props) {
  const pagesRef = useRef<HTMLDivElement>(null)
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [rendered, setRendered] = useState(false)
  const [containerWidth, setContainerWidth] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [currentPage, setCurrentPage] = useState(1)
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
  const numPages = doc?.numPages ?? 0

  // Keep PDF pages fitted to the actual preview pane. The field editor and
  // preview are responsive columns, so a fixed PDF scale clips both edges.
  useEffect(() => {
    const container = pagesRef.current
    if (!container || !isPdf) return

    const updateWidth = (width: number) => {
      const rounded = Math.floor(width)
      setContainerWidth((current) => (Math.abs(current - rounded) < 2 ? current : rounded))
    }
    const style = getComputedStyle(container)
    updateWidth(
      container.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
    )

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) updateWidth(entry.contentRect.width)
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [isPdf])

  // load document
  useEffect(() => {
    let cancelled = false
    setDoc(null)
    setRendered(false)
    setImageUrl(null)
    setZoom(1)
    setCurrentPage(1)
    if (!isPdf) {
      const url = URL.createObjectURL(file)
      setImageUrl(url)
      return () => URL.revokeObjectURL(url)
    }
    file.arrayBuffer().then(async (buf) => {
      const loaded = await pdfjs.getDocument({ data: buf }).promise
      if (!cancelled) setDoc(loaded)
    })
    return () => {
      cancelled = true
    }
  }, [file, isPdf])

  // render pages + text layers
  useEffect(() => {
    if (!doc || !pagesRef.current || containerWidth <= 0) return
    let cancelled = false
    const container = pagesRef.current
    container.innerHTML = ''
    setRendered(false)

    const renderAll = async () => {
      for (let n = 1; n <= doc.numPages; n++) {
        if (cancelled) return
        const page = await doc.getPage(n)
        const baseViewport = page.getViewport({ scale: 1 })
        const scale = Math.min(1.5, containerWidth / baseViewport.width) * zoom
        const viewport = page.getViewport({ scale })

        const pageDiv = document.createElement('div')
        pageDiv.className = 'pdf-page'
        pageDiv.dataset.page = String(n)
        pageDiv.style.width = `${viewport.width}px`
        pageDiv.style.height = `${viewport.height}px`

        const canvas = document.createElement('canvas')
        const outputScale = window.devicePixelRatio || 1
        canvas.width = Math.ceil(viewport.width * outputScale)
        canvas.height = Math.ceil(viewport.height * outputScale)
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`
        pageDiv.appendChild(canvas)

        const textDiv = document.createElement('div')
        textDiv.className = 'textLayer'
        // pdf.js text layer positions itself off this CSS variable
        textDiv.style.setProperty('--scale-factor', String(scale))
        pageDiv.appendChild(textDiv)

        container.appendChild(pageDiv)

        const ctx = canvas.getContext('2d')!
        ctx.setTransform(outputScale, 0, 0, outputScale, 0, 0)
        await page.render({ canvas, canvasContext: ctx, viewport }).promise
        await new TextLayer({
          textContentSource: page.streamTextContent(),
          container: textDiv,
          viewport,
        }).render()
      }
      if (!cancelled) setRendered(true)
    }
    renderAll()
    return () => {
      cancelled = true
    }
  }, [containerWidth, doc, zoom])

  // track the page currently in view for the toolbar indicator
  useEffect(() => {
    const container = pagesRef.current
    if (!container || !rendered) return
    const update = () => {
      const probe = container.scrollTop + container.clientHeight * 0.4
      let current = 1
      for (const page of container.querySelectorAll<HTMLElement>('.pdf-page')) {
        if (page.offsetTop > probe) break
        current = Number(page.dataset.page)
      }
      setCurrentPage(current)
    }
    update()
    container.addEventListener('scroll', update, { passive: true })
    return () => container.removeEventListener('scroll', update)
  }, [rendered])

  // apply highlight
  useEffect(() => {
    const container = pagesRef.current
    if (!container || !rendered) return
    for (const el of container.querySelectorAll('.textLayer .hl')) el.classList.remove('hl')
    if (!highlight) return

    const pages = [...container.querySelectorAll<HTMLElement>('.pdf-page')]
    if (pages.length === 0) return
    const stated = highlight.page
      ? pages.find((p) => p.dataset.page === String(highlight.page))
      : undefined
    // The reported page number can be off; search it first, then the rest.
    const searchOrder = stated ? [stated, ...pages.filter((p) => p !== stated)] : pages

    const target = highlight.rawText ? norm(highlight.rawText) : ''
    let matched: HTMLElement[] = []
    let matchedPage = stated ?? pages[0]
    if (target.length >= 3) {
      for (const pageDiv of searchOrder) {
        const entries = collectEntries(pageDiv)
        const occurrences = findOccurrences(entries, target)
        if (occurrences.length > 0) {
          matched = pickOccurrence(entries, occurrences, highlight.location).spans
          matchedPage = pageDiv
          break
        }
      }
    }
    for (const span of matched) span.classList.add('hl')
    // Scroll ONLY the pages container. scrollIntoView would also scroll every
    // other scrollable ancestor, including the text layer itself.
    const targetEl = matched[0] ?? matchedPage
    const delta = targetEl.getBoundingClientRect().top - container.getBoundingClientRect().top
    const goal =
      container.scrollTop + delta - (matched.length > 0 ? container.clientHeight / 2 : 12)
    container.scrollTo({ top: Math.max(0, goal), behavior: 'smooth' })
  }, [highlight, rendered])

  const goToPage = (n: number) => {
    const container = pagesRef.current
    const page = container?.querySelector<HTMLElement>(`.pdf-page[data-page="${n}"]`)
    if (!container || !page) return
    container.scrollTo({ top: page.offsetTop - 12, behavior: 'smooth' })
  }

  if (!isPdf && imageUrl) {
    return (
      <div className="pdf-preview pdf-preview-image">
        <img className="image-preview" src={imageUrl} alt={file.name} />
      </div>
    )
  }
  return (
    <div className="pdf-preview">
      <div className="pdf-toolbar">
        <button
          aria-label={t('preview.prevPage')}
          disabled={currentPage <= 1}
          onClick={() => goToPage(currentPage - 1)}
        >
          <ChevronUp size={15} />
        </button>
        <span className="pdf-toolbar-pages">{numPages > 0 ? `${currentPage} / ${numPages}` : '…'}</span>
        <button
          aria-label={t('preview.nextPage')}
          disabled={numPages === 0 || currentPage >= numPages}
          onClick={() => goToPage(currentPage + 1)}
        >
          <ChevronDown size={15} />
        </button>
        <span className="pdf-toolbar-sep" />
        <button
          aria-label={t('preview.zoomOut')}
          disabled={zoom <= MIN_ZOOM}
          onClick={() => setZoom((z) => Math.max(MIN_ZOOM, +(z - ZOOM_STEP).toFixed(2)))}
        >
          <ZoomOut size={15} />
        </button>
        <button
          className="pdf-toolbar-zoom"
          aria-label={t('preview.resetZoom')}
          onClick={() => setZoom(1)}
        >
          {Math.round(zoom * 100)}%
        </button>
        <button
          aria-label={t('preview.zoomIn')}
          disabled={zoom >= MAX_ZOOM}
          onClick={() => setZoom((z) => Math.min(MAX_ZOOM, +(z + ZOOM_STEP).toFixed(2)))}
        >
          <ZoomIn size={15} />
        </button>
      </div>
      <div className="pdf-pages" ref={pagesRef} />
    </div>
  )
}
