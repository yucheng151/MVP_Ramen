from pathlib import Path

from PIL import Image, ImageDraw


base = Path(__file__).resolve().parent / "print_set"


def build(paths: list[Path], output: Path, columns: int, label_prefix: str) -> None:
    images = [Image.open(path).convert("RGB") for path in paths]
    if not images:
        return
    cell_w = max(image.width for image in images)
    cell_h = max(image.height for image in images) + 24
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (path, image) in enumerate(zip(paths, images)):
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        sheet.paste(image, (x, y + 24))
        draw.text((x + 4, y + 4), f"{label_prefix}{path.stem}", fill="black")
    sheet.save(output)


single = sorted((base / "single").glob("Print*.png"), key=lambda p: int(p.stem[5:]))
build(single, base / "single_overview.png", 2, "")

full = sorted((base / "full").glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
for start in range(0, len(full), 12):
    chunk = full[start : start + 12]
    build(chunk, base / f"full_{start + 1:03d}_{start + len(chunk):03d}.png", 3, "Print11 ")
