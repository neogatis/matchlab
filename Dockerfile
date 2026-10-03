FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r /app/requirements-photo.txt \
    && python /app/scripts/reconstruct_baseline.py \
    && python /app/scripts/verify_baseline.py
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-u", "-m", "scripts.start_postgres_http"]
