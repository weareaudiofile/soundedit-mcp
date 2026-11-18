'use strict';
// Bridges Claude Desktop (MCP on stdin/stdout) to the app's agent
// endpoint on 127.0.0.1. Written by the app; see its Settings ▸ Agent.
const http = require('http');
const readline = require('readline');
const { execFile } = require('child_process');

const app = process.env.AGENT_APP_NAME || 'The app';
const port = Number(process.env.AGENT_PORT);
const token = process.env.AGENT_TOKEN || '';
const bundle = process.env.AGENT_BUNDLE_ID || '';
let launchArgs = [];
try { launchArgs = JSON.parse(process.env.AGENT_LAUNCH_ARGS || '[]'); } catch (_) { launchArgs = []; }
const waitMs = 1000 * (Number(process.env.AGENT_WAIT_SECONDS) || 45);
let launching = null;

function post(body) {
  return new Promise((resolve, reject) => {
    const request = http.request({
      host: '127.0.0.1', port, path: '/mcp', method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'Authorization': 'Bearer ' + token,
        'Content-Length': Buffer.byteLength(body)
      }
    }, (response) => {
      const chunks = [];
      response.on('data', (chunk) => chunks.push(chunk));
      response.on('end', () => resolve({
        status: response.statusCode, text: Buffer.concat(chunks).toString('utf8')
      }));
    });
    request.on('error', reject);
    request.setTimeout(120000, () => request.destroy(new Error('timed out')));
    request.end(body);
  });
}

function launch() {
  if (!launching && bundle) {
    process.stderr.write(`[bridge] nothing on port ${port}: opening ${bundle}\n`);
    launching = new Promise((resolve) => {
      execFile('/usr/bin/open', ['-g', '-b', bundle, '--args', ...launchArgs], () => resolve());
    });
  }
  return launching || Promise.resolve();
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function send(body) {
  const deadline = Date.now() + waitMs;
  for (;;) {
    try {
      return await post(body);
    } catch (error) {
      if (error.code !== 'ECONNREFUSED' || Date.now() > deadline) throw error;
      await launch();
      await sleep(500);
    }
  }
}

function fail(id, message) {
  if (id === undefined || id === null) return;
  const error = { code: -32000, message };
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id, error }) + '\n');
}

readline.createInterface({ input: process.stdin }).on('line', async (line) => {
  if (!line.trim()) return;
  let id;
  try { id = JSON.parse(line).id; } catch (_) { id = undefined; }
  try {
    const answer = await send(line);
    if (answer.status === 200 && answer.text.trim()) {
      process.stdout.write(answer.text.trim() + '\n');
    } else if (answer.status === 401) {
      fail(id, `${app} turned this connection away: its token has changed. `
        + `Make the extension again in ${app} ▸ Settings ▸ Agent.`);
    } else if (answer.status !== 202) {
      fail(id, `${app} answered HTTP ${answer.status}.`);
    }
  } catch (error) {
    process.stderr.write(`[bridge] ${error.message}\n`);
    fail(id, `${app} is not answering on port ${port}. Open ${app} and check that `
      + `Settings ▸ Agent is on.`);
  }
});