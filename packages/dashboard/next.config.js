/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Static export to out/ - the Dockerfile serves that directory via nginx.
  // Without this, next build only writes .next/ and any stale out/ folder
  // copied into the image keeps being served.
  output: 'export',
  images: {
    unoptimized: true,
  },
  trailingSlash: true,
}

module.exports = nextConfig