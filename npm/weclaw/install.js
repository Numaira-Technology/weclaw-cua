#!/usr/bin/env node
'use strict';

const fs = require('fs');

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@anthropic-ai/weclaw-darwin-arm64',
  'darwin-x64':   '@anthropic-ai/weclaw-darwin-x64',
  'linux-x64':    '@anthropic-ai/weclaw-linux-x64',
  'linux-arm64':  '@anthropic-ai/weclaw-linux-arm64',
  'win32-x64':    '@anthropic-ai/weclaw-win32-x64',
};

const platformKey = `${process.platform}-${process.arch}`;
const pkg = PLATFORM_PACKAGES[platformKey];

if (!pkg) {
  console.log(`weclaw: no binary for ${platformKey}, skipping`);
  process.exit(0);
}

const ext = process.platform === 'win32' ? '.exe' : '';

try {
  const binaryPath = require.resolve(`${pkg}/bin/weclaw${ext}`);
  if (process.platform !== 'win32') {
    fs.chmodSync(binaryPath, 0o755);
    console.log(`weclaw: set executable permission for ${platformKey}`);
  }
} catch {
  console.log(`weclaw: platform package ${pkg} not installed`);
  console.log('To fix: npm install --force @anthropic-ai/weclaw');
}
