"""Quick utility to dump the text of a PDF for review."""
from pypdf import PdfReader
import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\User\CascadeProjects\project\SmartVoice_Xenu (AutoRecovered).pdf"
out = sys.argv[2] if len(sys.argv) > 2 else "_pdf_dump.txt"
r = PdfReader(path)
with open(out, "w", encoding="utf-8") as f:
    f.write(f"TOTAL PAGES: {len(r.pages)}\n")
    for i, p in enumerate(r.pages):
        f.write(f"\n========== PAGE {i+1} ==========\n")
        f.write(p.extract_text() + "\n")
print(f"Dumped {len(r.pages)} pages -> {out}")
