'use strict';
// Glama's build check only (see stand-in.js): starts the stand-in on 127.0.0.1, then runs the real
// bridge, server/index.js (the script inside SoundEdit.mcpb), against it over stdio, so Glama can start
// the server and read its tools. People never run this file.
const path = require('path');
const { spawn } = require('child_process');
const { start } = require('./stand-in');

start().then((server) => {
  const bridge = spawn(process.execPath, [path.join(__dirname, '..', 'server', 'index.js')], {
    stdio: 'inherit',
    env: { ...process.env, AGENT_APP_NAME: 'SoundEdit', AGENT_PORT: String(server.address().port),
           AGENT_TOKEN: 'glama-build-check', AGENT_BUNDLE_ID: '' }
  });
  bridge.on('exit', (code) => { server.close(); process.exit(code === null ? 1 : code); });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => bridge.kill(signal));
});
