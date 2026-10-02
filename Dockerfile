FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN python /app/scripts/reconstruct_baseline.py && python /app/scripts/verify_baseline.py
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-u", "/app/app/legacy/matchlab_v7.py"]
