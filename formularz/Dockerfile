FROM python:3.13-alpine
RUN pip install --no-cache-dir flask==3.1.* gunicorn==23.*
WORKDIR /app
COPY app.py .
VOLUME /dane
EXPOSE 8000
# ponytail: jeden worker wystarcza (ruch = pojedyncze zgłoszenia); limiter IP
# w pamięci procesu działa poprawnie właśnie przy jednym workerze
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8000", "--timeout", "180", "app:app"]
