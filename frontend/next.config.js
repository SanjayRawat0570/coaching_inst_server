/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Back / forward restores the scroll position of the page you left.
  experimental: { scrollRestoration: true },
};

module.exports = nextConfig;
