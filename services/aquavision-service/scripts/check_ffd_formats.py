import httpx
import json

# 1. Fetch current HTML bulletin and save for analysis
r = httpx.get("https://ffd.pmd.gov.pk/bulletin/bulletin", timeout=15, follow_redirects=True)
with open("/tmp/ffd_current.html", "w") as f:
    f.write(r.text)
print(f"HTML bulletin: {len(r.text)} chars")
# Show key data-ffd attributes
import re
attrs = re.findall(r'data-ffd-(\w+)=["\']([^"\']+)["\']', r.text)
print(f"Found {len(attrs)} data-ffd attributes")
for name, val in attrs[:20]:
    print(f"  data-ffd-{name} = {val}")
print("  ...")

# 2. Download one sample PDF to check format
r2 = httpx.get("https://ffd.pmd.gov.pk/bulletin/79/download", timeout=15, follow_redirects=True)
with open("/tmp/ffd_sample.pdf", "wb") as f:
    f.write(r2.content)
print(f"\nSample PDF: {len(r2.content)} bytes")
