"""Profile-picture sanitizing.

Every upload is decoded with Pillow and re-encoded from pixels, which:
  - proves the file really is an image (the browser's Content-Type is not trusted),
  - drops ALL metadata, including EXIF GPS coordinates that phone photos often carry,
  - flattens animated GIFs to a still and discards any trailing payload bytes,
  - shrinks it to at most 512x512, which also saves storage and bandwidth.
"""

import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SIDE = 512
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs


class BadImage(ValueError):
    pass


def sanitize_image(data: bytes) -> tuple[bytes, str]:
    """Return (clean image bytes, file extension) or raise BadImage."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise BadImage("Profile picture must be under 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(data))
            fmt = probe.format
            probe.verify()  # structural check; the image must be reopened afterwards
            img = Image.open(io.BytesIO(data))
            img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise BadImage("That file isn't a valid image. Use a JPG, PNG, WEBP, or GIF.")
    if fmt not in ALLOWED_FORMATS:
        raise BadImage("Profile picture must be a JPG, PNG, WEBP, or GIF.")

    img = ImageOps.exif_transpose(img)  # keep phone photos upright before EXIF is dropped
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img.convert("RGBA").save(out, format="PNG", optimize=True)
        return out.getvalue(), ".png"
    img.convert("RGB").save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue(), ".jpg"
