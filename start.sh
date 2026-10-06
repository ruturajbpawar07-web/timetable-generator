#!/bin/sh
# API on localhost only; the Next.js server is the public entry point.
uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
cd frontend && HOSTNAME=0.0.0.0 exec node server.js
