# Vendored front-end libraries

Third-party JavaScript is committed here instead of being loaded from a CDN:
no requests to third-party servers (privacy/GDPR), works offline, and the exact version
is pinned and reviewed in git. Files are used as published; do not edit them.

| Library | Version | File | License | Source |
|---|---|---|---|---|
| [HTMX](https://htmx.org) | 2.0.11 | `htmx/htmx.min.js` | 0BSD (`htmx/LICENSE`) | `https://cdn.jsdelivr.net/npm/htmx.org@2.0.11/dist/htmx.min.js` |
| [Alpine.js](https://alpinejs.dev) | 3.17.5 | `alpinejs/alpine.min.js` | MIT (`alpinejs/LICENSE.md`) | `https://cdn.jsdelivr.net/npm/alpinejs@3.17.5/dist/cdn.min.js` |

SHA-256 checksums (to verify a file was not changed):

```text
d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717  htmx/htmx.min.js
b4036e9e9ac22fa6f6ae1ba292e015e1f3e9c85d0d79e73e4c8eb9bb139b522e  alpinejs/alpine.min.js
```

## Updating a library

1. Read the library's changelog for breaking changes.
2. Download the new version from the source URL above (change the version number).
3. Update the version, the checksum (`sha256sum <file>`) and this table.
4. Run the app and click through the pages that use it, then commit as `build(deps): update htmx to x.y.z`.
