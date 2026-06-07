FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

COPY tsconfig.json ./
COPY src ./src
RUN npm install typescript && npm run build && npm uninstall typescript && npm prune --omit=dev

ENV PORT=8001
EXPOSE 8001

CMD ["node", "dist/index.js"]
