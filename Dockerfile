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
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import os,urllib.request,urllib.parse; r=urllib.request.Request('http://127.0.0.1:8000/api/ready',headers={'Host':urllib.parse.urlsplit(os.environ['APP_ORIGIN']).netloc}); urllib.request.urlopen(r,timeout=4)" || exit 1
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
