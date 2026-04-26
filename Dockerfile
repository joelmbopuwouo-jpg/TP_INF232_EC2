FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV FLASK_ENV=production
ENV FLASK_APP=app2.py

# Expose default Flask port (gunicorn will bind to 8000 below)
EXPOSE 8000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app2:app"]
