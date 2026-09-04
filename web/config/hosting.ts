import { readFile } from 'node:fs/promises';

export interface HostingBindings {
  d1: string | null;
  r2: string | null;
  configured: boolean;
}

const DEFAULT_HOSTING_CONFIG_URL = new URL('../.openai/hosting.json', import.meta.url);
const EMPTY_HOSTING_BINDINGS: HostingBindings = { d1: null, r2: null, configured: false };

function isMissingFile(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    error.code === 'ENOENT'
  );
}

function parseHostingBindings(value: unknown): HostingBindings {
  if (typeof value !== 'object' || value === null) {
    throw new TypeError('Hosting configuration must be a JSON object');
  }

  const candidate = value as Record<string, unknown>;
  const validD1 = candidate.d1 === null || typeof candidate.d1 === 'string';
  const validR2 = candidate.r2 === null || typeof candidate.r2 === 'string';
  if (!validD1 || !validR2) {
    throw new TypeError('Hosting configuration d1 and r2 values must be strings or null');
  }

  return {
    d1: candidate.d1 as string | null,
    r2: candidate.r2 as string | null,
    configured: true,
  };
}

export async function loadHostingBindings(
  configUrl: URL = DEFAULT_HOSTING_CONFIG_URL,
): Promise<HostingBindings> {
  try {
    return parseHostingBindings(JSON.parse(await readFile(configUrl, 'utf8')));
  } catch (error) {
    if (isMissingFile(error)) return EMPTY_HOSTING_BINDINGS;
    throw error;
  }
}
