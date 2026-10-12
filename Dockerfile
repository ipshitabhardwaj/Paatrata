# Build the UI, then serve API + UI from one container (port 8000).
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY core ./core
RUN pip install --no-cache-dir -e ".[server,eval]"
COPY server ./server
COPY evaluation ./evaluation
COPY samples ./samples
COPY --from=web /web/dist ./web/dist
ENV DB_PATH=/app/data/paatrata.db PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
