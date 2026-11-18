'use strict';
// Glama's build check only. It is not part of the Claude extension or the Claude Code plugin, and
// it never runs on a person's Mac.
//
// SoundEdit's MCP server is part of the SoundEdit app for Mac. Glama's Linux build machine has no SoundEdit,
// so this stand-in plays SoundEdit's endpoint there: it answers the MCP handshake and tools/list with
// SoundEdit's real tool definitions (tools.json, read from SoundEdit's own server), and answers every
// tool call with an error that says what to install. It holds no data, makes no outside requests
// and listens on 127.0.0.1 only.
const http = require('http');
const fs = require('fs');
const path = require('path');

const SNAPSHOT = JSON.parse(fs.readFileSync(path.join(__dirname, 'tools.json'), 'utf8'));
const NOT_HERE = "This is Glama's build check, not SoundEdit. To use this tool, install SoundEdit for Mac "
  + '(https://audiofile.engineering/soundedit), turn on Settings ▸ Agent and connect your AI app: '
  + 'https://github.com/weareaudiofile/soundedit-mcp';

function answer(message) {
  switch (message.method) {
    case 'initialize':
      return {
        protocolVersion: (message.params && message.params.protocolVersion) || '2025-06-18',
        capabilities: { tools: {} },
        serverInfo: { name: SNAPSHOT.server.name, title: "SoundEdit (stand-in for Glama's build check)",
                      version: SNAPSHOT.server.version },
        instructions: SNAPSHOT.instructions
      };
    case 'tools/list': return { tools: SNAPSHOT.tools };
    case 'tools/call': return { isError: true, content: [{ type: 'text', text: NOT_HERE }] };
    case 'ping': return {};
    default: return undefined;
  }
}

function start(port = 0) {
  return new Promise((resolve) => {
    const server = http.createServer((request, response) => {
      const chunks = [];
      request.on('data', (chunk) => chunks.push(chunk));
      request.on('end', () => {
        if (request.method !== 'POST' || request.url !== '/mcp') { response.writeHead(404); response.end(); return; }
        if (!/^Bearer \S+/.test(String(request.headers.authorization || ''))) { response.writeHead(401); response.end(); return; }
        let message;
        try { message = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch (_) { response.writeHead(400); response.end(); return; }
        if (message.id === undefined || message.id === null) { response.writeHead(202); response.end(); return; }
        const result = answer(message);
        const reply = result === undefined
          ? { jsonrpc: '2.0', id: message.id, error: { code: -32601, message: 'no such method: ' + message.method } }
          : { jsonrpc: '2.0', id: message.id, result };
        const body = JSON.stringify(reply);
        response.writeHead(200, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
        response.end(body);
      });
    });
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

module.exports = { start };
