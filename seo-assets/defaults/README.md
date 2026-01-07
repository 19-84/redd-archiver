# Default SEO Assets

This directory contains default SEO assets that will be used when custom assets are not specified in the TOML configuration.

## Files

- `og-image.webp` - Default Open Graph image (1200x630px, WebP format)
- `og-image.png` - Default Open Graph image fallback (1200x630px, PNG format)
- `favicon.ico` - Default favicon with multiple sizes (16x16, 32x32, 48x48)
- `favicon.svg` - Default scalable favicon (SVG format)

## Usage

These files are automatically copied to the output directory when no custom SEO assets are specified in the TOML configuration. Custom assets should be placed in `seo-assets/[subreddit-name]/` directories.

## Creating Custom Assets

### Open Graph Images
- Recommended size: 1200x630px
- Use WebP format for best compression
- Include PNG fallback for compatibility
- Should represent the subreddit or archive content

### Favicons
- ICO format should include multiple sizes: 16x16, 32x32, 48x48
- SVG format provides scalability for modern browsers
- Keep design simple and recognizable at small sizes
