# One container: Next.js (public $PORT) proxies /api/* to FastAPI on 127.0.0.1:8000.

FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY scheduler/ scheduler/
COPY data/ data/
# generate the initial timetable at build time (build machines have far more CPU than a free instance)
RUN python -c "from backend.main import seed; seed()"
COPY --from=web /app/frontend/.next/standalone frontend/
COPY --from=web /app/frontend/.next/static frontend/.next/static
COPY start.sh .
ENV SOLVER_WORKERS=2 PORT=10000
EXPOSE 10000
CMD ["sh", "start.sh"]
