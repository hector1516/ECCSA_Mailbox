# Mailbox ECCSA — imagen de la app.
#
# Sin Node: el frontend se compila en CI (ubuntu-latest) y el resultado llega en
# dist/. El servidor de despliegue tiene 1 vCPU y 1.9 GB de RAM; compilar ahí no
# entra. Ver deploy/DEPLOY.md y el workflow deploy-linux.yml.
FROM python:3.11-slim

WORKDIR /app

# curl es solo para el HEALTHCHECK. pymssql viene en wheel manylinux y NO necesita
# freetds-dev para instalarse (a diferencia de compilando desde fuente).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/

# Frontend compilado por fuera (npm run build) y servido por FastAPI en "/".
COPY dist/ ./dist/

# Versión del shell común (ECCSA-Shell): la lee GET /api/shell/state para el
# banner. Es un archivo generado por tools/sync_shell.py.
COPY ECCSA_SHELL_VERSION ./ECCSA_SHELL_VERSION
COPY package.json ./package.json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
  CMD curl -f http://localhost:8000/health || exit 1

# Proceso único en primer plano (PID 1): si uvicorn cae, Docker lo reinicia.
# Para cargar código nuevo alcanza con `docker restart mailbox` — no hay
# supervisor, a diferencia de workersadmon.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
