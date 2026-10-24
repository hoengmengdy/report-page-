FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY data ./data
COPY migrations ./migrations
COPY index.py ./
COPY --from=frontend /build/dist ./dist
RUN groupadd --gid 10001 pagepulse && useradd --uid 10001 --gid pagepulse --no-create-home pagepulse \
    && mkdir -p /app/instance && chown pagepulse:pagepulse /app/instance
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "backend.serve"]
