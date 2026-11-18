# Glama's build check only: runs the real bridge (server/index.js) against a stand-in for SoundEdit's
# endpoint (glama/), because SoundEdit's MCP server runs inside the SoundEdit app for Mac.
FROM node:22-alpine
WORKDIR /app
COPY server ./server
COPY glama ./glama
CMD ["node", "glama/run.js"]
