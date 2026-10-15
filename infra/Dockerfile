FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# Match the packages used in the demo
RUN pip install --no-cache-dir \
    streamlit plotly pyspark pandas numpy scikit-learn scipy \
    pyarrow boto3 trino elasticsearch pytest mcp

COPY . /app

ENV OFFLINE_MODE=0
ENV PYTHONUNBUFFERED=1
ENV PYSPARK_PYTHON=python3
ENV PYSPARK_DRIVER_PYTHON=python3

EXPOSE 8501

CMD ["streamlit", "run", "app/dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
