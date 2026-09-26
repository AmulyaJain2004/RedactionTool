FROM python:3.12-slim

WORKDIR /app

# Dependencies first so Docker can cache this layer
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

COPY app.py redact.py ./
COPY pii_redactor pii_redactor

# Run as an unprivileged user
RUN useradd --create-home appuser
USER appuser

# Hosting platforms set PORT; default to 8000 locally
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2 --timeout 120"]
