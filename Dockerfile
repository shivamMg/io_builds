FROM python:2

ADD . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "/app/main.py"]
