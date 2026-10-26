interface Props {
  first: string
  last: string
  photo: string | null
  size?: number
}

// Profile picture, or initials on a blue disc when there isn't one.
export default function Avatar({ first, last, photo, size = 40 }: Props) {
  const style = { width: size, height: size, fontSize: size * 0.4 }
  if (photo) return <img className="avatar" src={photo} alt={`${first} ${last}`} style={style} />
  return (
    <span className="avatar avatar-initials" style={style} aria-hidden="true">
      {first.charAt(0)}{last.charAt(0)}
    </span>
  )
}
