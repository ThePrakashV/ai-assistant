FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Libraries modhalil. Code maathinaalum indha layer cache la irukkum (thirumba install aagaadhu)
COPY requirements-docker.txt .
RUN pip install -r requirements-docker.txt

# Code (venv, models, data, .env ellam .dockerignore la thavirkkirom)
COPY app ./app

# Root illaama run pannurom (safety)
RUN useradd --create-home nova
USER nova

EXPOSE 8000
CMD ["uvicorn", "app.monitor_main:app", "--host", "0.0.0.0", "--port", "8000"]