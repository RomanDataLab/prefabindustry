/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false, // Mapbox map flashes with double-mount
  poweredByHeader: false,
  images: {
    unoptimized: true,
  },
  webpack: (config, { dev }) => {
    if (dev) {
      // Prevent intermittent corrupted chunk/cache files on Windows dev runs.
      config.cache = false
    }
    return config
  },
}

module.exports = nextConfig
