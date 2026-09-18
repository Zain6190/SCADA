"""
Download all FFD bulletin PDFs from the archive.
FFD bulletin numbers go 1-81, each is a PDF.
"""
import httpx
import sys
import time
from pathlib import Path

OUTPUT_DIR = Path("/app/infrastructure/ingestion/raw_archive/ffl_pdfs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = httpx.Client(timeout=30, follow_redirects=True)
downloaded = 0
failed = []

for num in range(1, 82):
    url = f"https://ffd.pmd.gov.pk/bulletin/{num}/download"
    filename = f"FFD_{num:03d}.pdf"
    output = OUTPUT_DIR / filename
    
    if output.exists() and output.stat().st_size > 10000:
        print(f"#{num:03d} EXISTS ({output.stat().st_size:,} bytes)")
        downloaded += 1
        continue
    
    try:
        r = client.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 10000:
            output.write_bytes(r.content)
            print(f"#{num:03d} OK ({len(r.content):,} bytes)")
            downloaded += 1
            time.sleep(1)  # Be nice
        else:
            print(f"#{num:03d} SKIP (status={r.status_code}, size={len(r.content)})")
            failed.append(num)
    except Exception as e:
        print(f"#{num:03d} ERROR: {e}")
        failed.append(num)
        time.sleep(3)

client.close()
print(f"\n=== Done: {downloaded} downloaded, {len(failed)} failed ===")
if failed:
    print(f"Failed: {failed}")
