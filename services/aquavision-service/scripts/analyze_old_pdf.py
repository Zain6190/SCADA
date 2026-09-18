import pdfplumber

# Check an old PDF (before bulletins changed format)
for num in [1, 5, 10, 20, 30]:
    pdf_path = f"/app/infrastructure/ingestion/raw_archive/ffl_pdfs/FFD_{num:03d}.pdf"
    try:
        pdf = pdfplumber.open(pdf_path)
        print(f"\n=== FFD_{num:03d}.pdf ({len(pdf.pages)} pages) ===")
        # Check page 4 (index 3) for tables
        if len(pdf.pages) >= 4:
            page = pdf.pages[3]
            tables = page.extract_tables()
            text = page.extract_text() or ""
            print(f"  Tables found: {len(tables)}")
            print(f"  Text (first 1500 chars):")
            print(text[:1500])
            for ti, table in enumerate(tables):
                print(f"  Table {ti}: {len(table)} rows x {len(table[0]) if table else 0} cols")
                for row in table[:3]:
                    print(f"    {row}")
        else:
            page = pdf.pages[-1]
            text = page.extract_text() or ""
            print(f"  Only {len(pdf.pages)} pages, checking last page:")
            print(text[:1500])
        pdf.close()
    except Exception as e:
        print(f"  ERROR: {e}")
