/**
 * App version, inlined at build time by Vite from the repo-root VERSION file
 * (see `define` in vite.config.ts). That file is the single source of truth —
 * the backend reads the same one for its OpenAPI version and /api/version.
 *
 * Bump VERSION and tag the release together (`./scripts/release.sh X.Y.Z`);
 * nothing derives this from git, because .git is excluded from the Docker
 * build context.
 */
import { readable } from 'svelte/store';

declare const __APP_VERSION__: string;

export const APP_VERSION: string = __APP_VERSION__;

export interface DeployedVersion {
  version: string;
  commit: string;
  ref: string;
}

const UNKNOWN = 'unknown';

/**
 * The label shown under the logo.
 *
 * A clean release reads `v0.2.0`. Anything else — deployed from `main`, a
 * hand-built image, or a bundle that disagrees with the server — gets a
 * suffix like `v0.2.0 (main@e4230a8)` so a dev build is never mistaken for a
 * release.
 */
export function formatVersionLabel(deployed: DeployedVersion | null): string {
  if (!deployed) return `v${APP_VERSION}`;

  const ref = deployed.ref && deployed.ref !== UNKNOWN ? deployed.ref : '';
  const commit =
    deployed.commit && deployed.commit !== UNKNOWN ? deployed.commit.slice(0, 7) : '';

  // Exactly the release it claims to be, and the bundle agrees.
  if (ref === `v${deployed.version}` && deployed.version === APP_VERSION) {
    return `v${deployed.version}`;
  }

  const detail = [ref, commit].filter(Boolean).join('@') || UNKNOWN;
  return `v${deployed.version} (${detail})`;
}

export function formatVersionTitle(deployed: DeployedVersion | null): string {
  if (!deployed) return `App version (build ${APP_VERSION})`;
  const parts = [`server v${deployed.version}`, `ref ${deployed.ref}`, `commit ${deployed.commit}`];
  if (deployed.version !== APP_VERSION) parts.push(`bundle v${APP_VERSION} — MISMATCH`);
  return parts.join(' · ');
}

async function fetchDeployedVersion(): Promise<DeployedVersion | null> {
  try {
    // Unauthenticated endpoint; no cookie needed and none wanted.
    const res = await fetch('/api/version', { credentials: 'omit' });
    if (!res.ok) return null;
    const data = (await res.json()) as Partial<DeployedVersion>;
    if (typeof data?.version !== 'string') return null;
    return {
      version: data.version,
      commit: typeof data.commit === 'string' ? data.commit : UNKNOWN,
      ref: typeof data.ref === 'string' ? data.ref : UNKNOWN,
    };
  } catch {
    // Offline / installed PWA with no server reachable. Degrade to the
    // build-time version rather than showing nothing.
    return null;
  }
}

/**
 * Resolves to the deployed version once, on first subscribe. Deliberately not
 * baked into the JS bundle: the SPA is built in an earlier Docker stage, so
 * baking the SHA would mean rebuilding the whole frontend to change a label.
 */
export const deployedVersion = readable<DeployedVersion | null>(null, (set) => {
  let cancelled = false;
  fetchDeployedVersion().then((v) => {
    if (!cancelled) set(v);
  });
  return () => {
    cancelled = true;
  };
});
