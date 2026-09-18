import pdfplumber

pdf_path = "/app/infrastructure/ingestion/raw_archive/ffl_pdfs/FFD_079.pdf"
pdf = pdfplumber.open(pdf_path)
print(f"Pages: {len(pdf.pages)}")

# Extract text from first 3 pages to understand structure
for i, page in enumerate(pdf.pages[:4]):
    text = page.extract_text()
    if text:
        print(f"\n=== Page {i+1} (first 2000 chars) ===")
        print(text[:2000])

# Also try extracting tables
for i, page in enumerate(pdf.pages[:4]):
    tables = page.extract_tables()
    if tables:
        print(f"\n=== Tables on Page {i+1} ===")
        for ti, table in enumerate(tables):
            print(f"  Table {ti}: {len(table)} rows x {len(table[0]) if table else 0} cols")
            for row in table[:5]:
                print(f"    {row}")

pdf.close()
