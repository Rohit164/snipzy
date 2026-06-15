FROM python:3.11-slim

# Install ffmpeg and system deps
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces runs as non-root user 1000
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /home/user/app

# Copy everything first
COPY --chown=user . .

# Install Python deps explicitly
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    flask \
    opencv-python-headless \
    numpy \
    rapidocr-onnxruntime

# Create required dirs
RUN mkdir -p uploads outputs

EXPOSE 7860

CMD ["python", "app.py"]
