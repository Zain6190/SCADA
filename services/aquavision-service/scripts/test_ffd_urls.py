import httpx

urls = [
    "https://ffd.pmd.gov.pk/bulletin/79/download",
    "https://ffd.pmd.gov.pk/bulletin/bulletin",
    "https://ffd.pmd.gov.pk/bulletins/FFD_01-01-2025.html",
    "https://ffd.pmd.gov.pk/ffdbulletin/FFD_01-01-2025.html",
]
for u in urls:
    try:
        r = httpx.get(u, timeout=10, follow_redirects=True)
        ct = r.headers.get("content-type", "?")
        print(f"{u}: status={r.status_code}, size={len(r.content)}, type={ct}")
    except Exception as e:
        print(f"{u}: ERROR {e}")
