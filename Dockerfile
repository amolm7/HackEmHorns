FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production AUTH_MODE=password
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home agent
COPY backend ./backend
COPY static ./static
COPY scripts ./scripts
COPY server.py ./server.py
RUN mkdir -p /app/data && chown -R agent:agent /app
USER agent
EXPOSE 8000 10000
# Render supplies PORT (10000 by default); locally it falls back to 8000. The probe uses the liveness route,
# which accepts any Host header, so it works behind a host's own health checks as well.
ENV PORT=8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/api/health',timeout=4)" || exit 1
# Behind a host's load balancer every request comes from the proxy, so trust X-Forwarded-For for per-client limits.
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT} --workers 1 --no-access-log --proxy-headers --forwarded-allow-ips='*'"]
