# 构建阶段：含 devDependencies，产出 dist/
FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# 运行阶段：仅生产依赖 + dist，非 root 运行
FROM node:22-slim

WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8001

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /app/dist ./dist

USER node
EXPOSE 8001

CMD ["node", "dist/index.js"]
