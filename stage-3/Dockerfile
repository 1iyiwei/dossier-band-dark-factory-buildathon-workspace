FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080 DATA_DIR=/var/lib/dossier
WORKDIR /app

# Provider SDKs come from PyPI at build time; nothing is fetched at run time.
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY dossier_service ./dossier_service

# The state journal lives on the container's filesystem, which survives a container restart.
RUN mkdir -p "$DATA_DIR"

EXPOSE 8080
CMD ["python", "-m", "dossier_service"]
