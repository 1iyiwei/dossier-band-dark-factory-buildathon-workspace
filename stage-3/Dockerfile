FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080
WORKDIR /app

# Provider SDKs come from PyPI at build time; nothing is fetched at run time.
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY dossier_service ./dossier_service

EXPOSE 8080
CMD ["python", "-m", "dossier_service"]
