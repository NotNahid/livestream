# Runs the whole stack in one container: Xvfb + Chromium + PulseAudio + FFmpeg.
# Playwright's image already contains Chromium and its system libraries.
FROM mcr.microsoft.com/playwright/python:v1.65.2-jammy

RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb ffmpeg pulseaudio curl procps \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir "playwright==1.49.1"

COPY . .
RUN chmod +x ./*.sh scripts/*.sh

# The control panel is reachable from outside the container, so it needs a token.
ENV BIND=0.0.0.0 PORT=8080
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD curl -fs http://127.0.0.1:8080/api/health || exit 1

CMD ["./run.sh"]
