import re, pdfplumber
from pathlib import Path

PDF_DIR = Path("/app/infrastructure/ingestion/raw_archive/ffl_pdfs")
results = []

for pdf_path in sorted(PDF_DIR.glob("FFD_*.pdf")):
    try:
        pdf = pdfplumber.open(str(pdf_path))
        text = pdf.pages[0].extract_text() or ""
        # Extract date
        m = re.search(r'Dated:\s*(\d{1,2})\w*\s+(\w+)-(\d{4})', text)
        if m:
            day, month, year = m.groups()
            month_map = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
                         "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
            mn = month_map.get(month.lower(), 0)
            pages = len(pdf.pages)
            results.append((pdf_path.name, f"{year}-{mn:02d}-{int(day):02d}", pages))
        pdf.close()
    except:
        pass

results.sort(key=lambda x: x[1])
for name, dt, pages in results:
    marker = " [FULL]" if pages >= 5 else " [SHORT]"
    print(f"{name}: {dt} ({pages} pages){marker}")
print(f"\nTotal: {len(results)} bulletins")
