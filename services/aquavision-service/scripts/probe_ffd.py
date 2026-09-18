import httpx

# FFD uses bulletin numbers, not dates. Let's probe recent bulletins.
# Bulletin 79 = Aug 20, 2026 (from our earlier search)
# Try bulletins 1-80 to find the date range
found = []
for num in range(1, 82):
    url = f"https://ffd.pmd.gov.pk/bulletin/{num}/download"
    try:
        r = httpx.head(url, timeout=5, follow_redirects=True)
        if r.status_code == 200:
            ct = r.headers.get("content-type", "?")
            cl = r.headers.get("content-length", "?")
            found.append((num, ct, cl))
    except:
        pass

print(f"Found {len(found)} bulletins")
for num, ct, cl in found[:5]:
    print(f"  #{num}: {ct}, {cl} bytes")
print("  ...")
for num, ct, cl in found[-5:]:
    print(f"  #{num}: {ct}, {cl} bytes")
