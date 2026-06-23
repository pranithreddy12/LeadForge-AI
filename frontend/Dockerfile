FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@9 --activate
WORKDIR /app

COPY package.json ./
RUN pnpm install --no-frozen-lockfile

COPY . .
EXPOSE 3001
CMD ["pnpm", "dev"]
