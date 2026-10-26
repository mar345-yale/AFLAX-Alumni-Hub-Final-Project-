import { useEffect, useMemo } from 'react'
import Avatar from './Avatar'

interface Props {
  first: string
  last: string
  current: string | null
  file: File | null
  onFile: (file: File | null) => void
}

export default function PhotoPicker({ first, last, current, file, onFile }: Props) {
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  return (
    <div className="photo-picker">
      <Avatar first={first || '?'} last={last || ''} photo={preview ?? current} size={72} />
      <label className="btn btn-outline btn-sm">
        {file || current ? 'Change photo' : 'Add profile picture'}
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          hidden
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
      </label>
      {file && <button type="button" className="link-btn" onClick={() => onFile(null)}>Remove</button>}
      <small className="muted">JPG, PNG, WEBP, or GIF · up to 5 MB</small>
    </div>
  )
}
