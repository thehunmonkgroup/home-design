import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { loadHostingBindings } from './hosting';

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true })),
  );
});

async function createTemporaryConfigPath(): Promise<{ directory: string; path: string }> {
  const directory = await mkdtemp(join(tmpdir(), 'home-design-hosting-'));
  temporaryDirectories.push(directory);
  return { directory, path: join(directory, 'hosting.json') };
}

describe('hosting configuration', () => {
  it('uses empty local bindings when developer-specific configuration is absent', async () => {
    const { path } = await createTemporaryConfigPath();

    await expect(loadHostingBindings(pathToFileURL(path))).resolves.toEqual({
      d1: null,
      r2: null,
      configured: false,
    });
  });

  it('loads resource bindings without exposing unrelated deployment metadata', async () => {
    const { path } = await createTemporaryConfigPath();
    await writeFile(
      path,
      JSON.stringify({ project_id: 'local-project', d1: 'designs', r2: 'models' }),
      'utf8',
    );

    await expect(loadHostingBindings(pathToFileURL(path))).resolves.toEqual({
      d1: 'designs',
      r2: 'models',
      configured: true,
    });
  });

  it('rejects malformed resource bindings', async () => {
    const { path } = await createTemporaryConfigPath();
    await writeFile(path, JSON.stringify({ d1: 42, r2: null }), 'utf8');

    await expect(loadHostingBindings(pathToFileURL(path))).rejects.toThrow(
      'd1 and r2 values must be strings or null',
    );
  });
});
