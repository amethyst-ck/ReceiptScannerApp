# Canasta web-image overlay for ReceiptScanner.
#
# Its one job is to raise PHP's max_file_uploads. Stock Canasta is 20,
# which silently caps multi-file bulk uploads to 20 files (the rest never
# reach the server). Canasta exposes the other upload knobs via .env
# (PHP_UPLOAD_MAX_FILESIZE, PHP_POST_MAX_SIZE, PHP_MAX_INPUT_VARS) but not
# max_file_uploads, so bulk uploads need a derived image. The related
# limits are set here alongside it to keep upload config in one place.
#
# (Ghostscript + poppler-utils — for PdfHandler PDF thumbnails — used to
# be added here, but they now ship in the stock Canasta image.)
#
# Base Canasta image. Defaults to the published latest; override at build
# time with --build-arg BASE_IMAGE=... (e.g. Wicker's --base-image, to build
# against a custom or unreleased Canasta image). Pin the default tag to the
# Canasta version your instance runs.
ARG BASE_IMAGE=ghcr.io/canastawiki/canasta:latest
FROM ${BASE_IMAGE}

# Applied to every PHP SAPI present (fpm for web, cli for maintenance).
RUN set -eux; for d in /etc/php/*/*/conf.d/; do \
        [ -d "$d" ] || continue; \
        printf 'max_file_uploads = 200\npost_max_size = 200M\nupload_max_filesize = 20M\nmax_input_vars = 5000\n' \
            > "$d/zz-receiptscanner.ini"; \
    done
