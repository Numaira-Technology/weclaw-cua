#!/usr/bin/env node

const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@anthropic-ai/weclaw-darwin-arm64',
  'darwin-x64':   '@anthropic-ai/weclaw-darwin-x64',
  'linux-x64':    '@anthropic-ai/weclaw-linux-x64',
  'linux-arm64':  '@anthropic-ai/weclaw-linux-arm64',
  'win32-x64':    '@anthropic-ai/weclaw-win32-x64',
};

const platformKey = `${process.platform}-${process.arch}`;
const ext = process.platform === 'win32' ? '.exe' : '';

function getBinaryPath() {
  if (process.env.WECLAW_BINARY) {
    return process.env.WECLAW_BINARY;
  }

  const pkg = PLATFORM_PACKAGES[platformKey];
  if (!pkg) {
    console.error(`weclaw: unsupported platform ${platformKey}`);
    process.exit(1);
  }

  try {
    return require.resolve(`${pkg}/bin/weclaw${ext}`);
  } catch {
    const modPath = path.join(
      path.dirname(require.resolve(`${pkg}/package.json`)),
      `bin/weclaw${ext}`
    );
    if (fs.existsSync(modPath)) return modPath;
  }

  console.error(`weclaw: binary not found for ${platformKey}`);
  console.error('Try: npm install --force @anthropic-ai/weclaw');
  process.exit(1);
}

try {
  execFileSync(getBinaryPath(), process.argv.slice(2), {
    stdio: 'inherit',
    env: { ...process.env },
  });
} catch (e) {
  if (e && e.status != null) process.exit(e.status);
  throw e;
}
