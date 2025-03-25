FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget curl unzip fonts-liberation libasound2 libatk-bridge2.0-0 libgtk-3-0 libgbm-dev libnss3 lsb-release gnupg \
    libxshmfence1 libxss1 libappindicator3-1 libu2f-udev

RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable

COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir
RUN pip install -r requirements.txt --no-cache-dir
RUN pip install gunicorn --no-cache-dir

COPY . .

EXPOSE 8000

CMD ["gunicorn", "TrackMatch.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2"]
