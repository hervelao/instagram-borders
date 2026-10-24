#!/usr/bin/env python3
"""
border.py - place photos on a white Instagram canvas so they show in full.

Examples
  python3 border.py photo.jpg                 # one photo -> ./bordered/
  python3 border.py ~/Pictures/Q3-export       # a whole folder (Alan Schaller look)
  python3 border.py photos --ratio 4:5 --margin 0.05   # 1080x1350 canvas, white on all sides
  python3 border.py photos --out ~/Desktop/insta

Requires: Python 3.9+ and Pillow  (pip install pillow)
DNG files also need rawpy        (pip install rawpy)
"""
import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageCms, ImageFilter, ImageOps

RATIOS = {"4:5": (4, 5), "3:4": (3, 4), "1:1": (1, 1)}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic"}
RAW_EXT = {".dng"}
SRGB = ImageCms.createProfile("sRGB")
SRGB_BYTES = ImageCms.ImageCmsProfile(SRGB).tobytes()


def load(path: Path) -> Image.Image:
    """Open an image, apply camera rotation and convert it to sRGB."""
    if path.suffix.lower() in RAW_EXT:
        try:
            import rawpy
        except ImportError:
            sys.exit("DNG needs rawpy: pip install rawpy (or export JPEGs from Lightroom first)")
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, output_bps=8)  # sRGB by default
        return Image.fromarray(rgb)

    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    icc = img.info.get("icc_profile")
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if icc:  # e.g. Adobe RGB or Display P3 export -> sRGB, as Instagram expects
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            img = ImageCms.profileToProfile(img.convert("RGB"), src, SRGB,
                                            renderingIntent=ImageCms.Intent.PERCEPTUAL,
                                            outputMode="RGB")
        except ImageCms.PyCMSError:
            pass
    return img.convert("RGB")


def frame(img: Image.Image, width: int, ratio: str, margin: float,
          color: str, sharpen: bool, grid: bool = False) -> Image.Image:
    rw, rh = RATIOS[ratio]
    cw, ch = width, round(width * rh / rw)
    pad = round(cw * margin)                       # minimum white space on every side
    box_w, box_h = cw - 2 * pad, ch - 2 * pad
    scale = min(box_w / img.width, box_h / img.height)
    new = (round(img.width * scale), round(img.height * scale))

    small = img.resize(new, Image.Resampling.LANCZOS, reducing_gap=3.0)
    if sharpen:  # restores a little crispness lost when shrinking ~9500px to ~1000px
        small = small.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=2))

    canvas = Image.new("RGB", (cw, ch), color)
    canvas.paste(small, ((cw - new[0]) // 2, (ch - new[1]) // 2))
    if grid:  # pad to 3:4 so the profile grid shows the whole canvas, white above and below
        tall = Image.new("RGB", (cw, round(cw * 4 / 3)), color)
        tall.paste(canvas, (0, (tall.height - ch) // 2))
        return tall
    return canvas


def main() -> None:
    p = argparse.ArgumentParser(description="Put photos on a white Instagram canvas, uncropped.")
    p.add_argument("input", type=Path, help="a photo or a folder of photos")
    p.add_argument("--out", type=Path, default=Path("bordered"), help="output folder (default: ./bordered)")
    p.add_argument("--ratio", choices=RATIOS, default="1:1",
                   help="canvas shape: 1:1 = 1080x1080 (default, Alan Schaller look), 4:5 = 1080x1350, 3:4 = 1080x1440")
    p.add_argument("--width", type=int, default=1080, help="canvas width in px (default 1080, Instagram's size)")
    p.add_argument("--margin", type=float, default=0.0,
                   help="minimum border as a fraction of canvas width (default 0: the photo touches the edges "
                        "on its long side, so white shows only on the short side)")
    p.add_argument("--color", default="white", help="border colour (default white)")
    p.add_argument("--grid", action="store_true",
                   help="output 1080x1440 (3:4) so Instagram's grid shows white above and below "
                        "(the opened post then shows it too)")
    p.add_argument("--no-sharpen", action="store_true", help="skip the light sharpening after resizing")
    p.add_argument("--quality", type=int, default=95, help="JPEG quality (default 95)")
    a = p.parse_args()

    exts = IMAGE_EXT | RAW_EXT
    files = sorted(f for f in a.input.iterdir() if f.suffix.lower() in exts) if a.input.is_dir() else [a.input]
    if not files:
        sys.exit(f"No photos found in {a.input}")
    a.out.mkdir(parents=True, exist_ok=True)

    for f in files:
        try:
            out = frame(load(f), a.width, a.ratio, a.margin, a.color, not a.no_sharpen, a.grid)
        except Exception as e:  # keep going through the batch
            print(f"skip {f.name}: {e}")
            continue
        dest = a.out / f"{f.stem}_ig.jpg"
        out.save(dest, "JPEG", quality=a.quality, subsampling=0, optimize=True, icc_profile=SRGB_BYTES)
        print(f"{f.name} -> {dest}")


if __name__ == "__main__":
    main()
