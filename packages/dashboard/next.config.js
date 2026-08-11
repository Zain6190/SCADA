/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'export',  // ← Important: Static export for GitHub Pages
  images: {
    unoptimized: true,  // ← Required for static export
  },
  basePath: process.env.NODE_ENV === 'production' ? '/IBCP-SCADA' : '',
  assetPrefix: process.env.NODE_ENV === 'production' ? '/IBCP-SCADA' : '',
  trailingSlash: true,
}

module.exports = nextConfig