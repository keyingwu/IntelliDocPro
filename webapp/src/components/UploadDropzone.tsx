import { UploadCloud } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import './dropzone.css'

const ACCEPT = '.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg'

interface Props {
  multiple?: boolean
  onFiles: (files: File[]) => void
  title: string
  body: string
  buttonLabel: string
  compact?: boolean
  children?: ReactNode
}

export default function UploadDropzone({ multiple, onFiles, title, body, buttonLabel, compact, children }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handle = (list: FileList | null) => {
    if (!list || list.length === 0) return
    onFiles(Array.from(list))
  }

  return (
    <div
      className={`dropzone${dragging ? ' dragging' : ''}${compact ? ' compact' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        handle(e.dataTransfer.files)
      }}
    >
      <span className="dropzone-icon">
        <UploadCloud size={compact ? 20 : 26} />
      </span>
      <div className="dropzone-title">{title}</div>
      <div className="dropzone-body">{body}</div>
      <button className="btn btn-ghost" onClick={() => inputRef.current?.click()}>
        {buttonLabel}
      </button>
      {children}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple={multiple}
        hidden
        onChange={(e) => {
          handle(e.target.files)
          e.target.value = ''
        }}
      />
    </div>
  )
}
