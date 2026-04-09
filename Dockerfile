FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

ENV PORT=8080
ENV DB_PATH=/data/bot.db

EXPOSE 8080

CMD ["python", "main.py"]
