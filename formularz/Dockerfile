FROM python:3.15-alpine
RUN apk update && apk upgrade --no-cache \
    && pip install --no-cache-dir --upgrade pip "flask==3.1.*" "gunicorn==27.*"
WORKDIR /app
COPY app.py logo-mail.png ./
VOLUME /dane
EXPOSE 8000
# ponytail: jeden worker wystarcza (ruch = pojedyncze zgłoszenia); limiter IP
# w pamięci procesu działa poprawnie właśnie przy jednym workerze
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8000", "--timeout", "180", "app:app"]
