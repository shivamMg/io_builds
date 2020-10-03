FROM python:2 AS builder
ADD . /app
WORKDIR /app

# We are installing a dependency here directly into our app source dir
RUN pip install --target=/app requests PyYAML

ENV PYTHONPATH /app
CMD ["python", "/app/main.py"]
