FROM python:3.11-slim

WORKDIR /app


RUN apt-get update && apt-get install -y \
    wget curl unzip gnupg \
    fonts-liberation libasound2 libatk-bridge2.0-0 libgtk-3-0 \
    libgbm-dev libnss3 libxshmfence1 libxss1 libappindicator3-1 libu2f-udev \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt && pip install gunicorn

COPY . .

EXPOSE 8000

CMD ["gunicorn", "TrackMatch.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2"]
