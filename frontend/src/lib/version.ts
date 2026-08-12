/**
 * App version, inlined at build time by Vite from the repo-root VERSION file
 * (see `define` in vite.config.ts). That file is the single source of truth —
 * the backend reads the same one for its OpenAPI version and /api/version.
 *
 * Bump VERSION and tag the release together; nothing derives this from git,
 * because .git is excluded from the Docker build context.
 */
declare const __APP_VERSION__: string;

export const APP_VERSION: string = __APP_VERSION__;
