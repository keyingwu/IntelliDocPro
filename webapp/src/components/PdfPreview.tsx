import * as pdfjs from 'pdfjs-dist'
import { TextLayer } from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import { useEffect, useRef, useState } from 'react'
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

const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase()

interface Props {
  file: File
  highlight: Highlight | null
}

/** Renders a PDF (all pages) or an image, with text-layer highlighting.
 * Highlighting matches the extraction's raw_text against text-layer spans on
 * the source page; scanned PDFs (no text layer) degrade to page scroll +
 * the location banner shown by the parent. */
export default function PdfPreview({ file, highlight }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [rendered, setRendered] = useState(false)
  const [containerWidth, setContainerWidth] = useState(0)
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')

  // Keep PDF pages fitted to the actual preview pane. The field editor and
  // preview are responsive columns, so a fixed PDF scale clips both edges.
  useEffect(() => {
    const container = containerRef.current
    if (!container || !isPdf) return

    const updateWidth = (width: number) => {
      const rounded = Math.floor(width)
      setContainerWidth((current) => (Math.abs(current - rounded) < 2 ? current : rounded))
    }
    updateWidth(container.clientWidth)

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
    if (!doc || !containerRef.current || containerWidth <= 0) return
    let cancelled = false
    const container = containerRef.current
    container.innerHTML = ''
    setRendered(false)

    const renderAll = async () => {
      for (let n = 1; n <= doc.numPages; n++) {
        if (cancelled) return
        const page = await doc.getPage(n)
        const baseViewport = page.getViewport({ scale: 1 })
        const scale = Math.min(1.5, containerWidth / baseViewport.width)
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
  }, [containerWidth, doc])

  // apply highlight
  useEffect(() => {
    const container = containerRef.current
    if (!container || !rendered) return
    for (const el of container.querySelectorAll('.textLayer .hl')) el.classList.remove('hl')
    if (!highlight) return

    const pageDiv = highlight.page
      ? container.querySelector<HTMLElement>(`.pdf-page[data-page="${highlight.page}"]`)
      : container.querySelector<HTMLElement>('.pdf-page')
    if (!pageDiv) return

    let matched: HTMLElement | null = null
    const target = highlight.rawText ? norm(highlight.rawText) : ''
    if (target.length >= 3) {
      const spans = pageDiv.querySelectorAll<HTMLElement>('.textLayer span')
      for (const span of spans) {
        const text = norm(span.textContent ?? '')
        if (text.length < 3) continue
        if (target.includes(text) || text.includes(target)) {
          span.classList.add('hl')
          matched ??= span
        }
      }
    }
    ;(matched ?? pageDiv).scrollIntoView({ behavior: 'smooth', block: matched ? 'center' : 'start' })
  }, [highlight, rendered])

  if (!isPdf && imageUrl) {
    return (
      <div className="pdf-preview">
        <img className="image-preview" src={imageUrl} alt={file.name} />
      </div>
    )
  }
  return <div className="pdf-preview" ref={containerRef} />
}
