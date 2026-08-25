from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent


def sheets(folder: Path, prefix: str, cols: int = 4, rows: int = 4) -> None:
    files = sorted(folder.glob("*.png"))
    font = ImageFont.load_default()
    for batch_no, start in enumerate(range(0, len(files), cols * rows), 1):
        batch = files[start:start + cols * rows]
        thumbs = []
        for path in batch:
            im = Image.open(path).convert("RGB")
            im.thumbnail((500, 340))
            tile = Image.new("RGB", (520, 380), "white")
            tile.paste(im, ((520 - im.width) // 2, 25))
            ImageDraw.Draw(tile).text((8, 7), path.stem, fill="black", font=font)
            thumbs.append(tile)
        sheet = Image.new("RGB", (cols * 520, rows * 380), "#dddddd")
        for i, tile in enumerate(thumbs):
            sheet.paste(tile, ((i % cols) * 520, (i // cols) * 380))
        sheet.save(ROOT / f"{prefix}-{batch_no:02d}.jpg", quality=88)


sheets(ROOT / "numbered", "numbered", cols=3, rows=5)
sheets(ROOT / "pdf14", "pdf14")
sheets(ROOT / "pdf15", "pdf15")
