import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const scriptsDirectory = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptsDirectory, '..');

export const projectPaths = {
  root,
  artifactsDir: path.join(root, 'artifacts'),
  fixtureDir: path.join(root, 'tests', 'fixtures'),
  playwrightDir: path.join(root, 'output', 'playwright'),
  browserOptions: process.env.PLAYWRIGHT_EXECUTABLE_PATH
    ? { headless: true, executablePath: path.resolve(process.env.PLAYWRIGHT_EXECUTABLE_PATH) }
    : { headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge' },
};

export function loadChromium() {
  const packageManifest = process.env.PLAYWRIGHT_PACKAGE_JSON;
  const require = packageManifest
    ? createRequire(path.resolve(packageManifest))
    : createRequire(import.meta.url);

  try {
    return require('playwright');
  } catch (error) {
    throw new Error(
      'Playwright is required for browser checks. Install it in this project or set PLAYWRIGHT_PACKAGE_JSON.',
      { cause: error },
    );
  }
}

export async function prepareQaDirectories() {
  await Promise.all([
    mkdir(projectPaths.artifactsDir, { recursive: true }),
    mkdir(projectPaths.playwrightDir, { recursive: true }),
  ]);
}
