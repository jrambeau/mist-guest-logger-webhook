FROM python:3.9-slim

# Set Python to run in unbuffered mode
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3000

# Run Gunicorn with stdout/stderr logging and access logs to stdout
CMD ["gunicorn", "--workers=4", "--bind=0.0.0.0:3000", \
     "--access-logfile=-", "--error-logfile=-", \
     "--capture-output", "--enable-stdio-inheritance", \
     "mist-guest-logger-webhook:app"]
