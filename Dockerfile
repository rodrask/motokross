FROM python:3.9-slim-buster
WORKDIR /app

ADD requirements.txt .
RUN pip3 install -r requirements.txt

ADD motokross ./motokross
ADD static ./static
ADD templates ./templates

ENV PORT 8877

EXPOSE "${PORT}"

CMD ["python", "-m", "motokross.server", "--data", "/moto/data", "--config", "/moto/config.json", "--port", "8877" ]
