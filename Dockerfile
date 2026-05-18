FROM python:3.11-slim

# Install system deps (if needed) and set workdir
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . /app

EXPOSE 8501

CMD ["streamlit", "run", "streamlit_bca_app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
