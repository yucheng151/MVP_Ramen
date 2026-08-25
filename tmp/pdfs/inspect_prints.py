from pathlib import Path

from pypdf import PdfReader


root = Path(__file__).resolve().parents[2] / "1.PLC" / "MVP_V2_100"
for number in range(1, 12):
    path = root / f"Print{number}.pdf"
    reader = PdfReader(str(path))
    print(f"### {path.name} pages={len(reader.pages)}")
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").replace("\x00", " ").replace("\n", " | ")
        print(f"PAGE {page_number}: {text[:900]}")
