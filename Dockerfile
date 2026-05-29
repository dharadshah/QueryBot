# Base image — Python 3.11 slim
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for pyodbc and MSSQL
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unixodbc \
    unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==2.4.1

# Copy dependency files first for layer caching
COPY pyproject.toml poetry.lock ./

# Install dependencies — no dev dependencies in production
RUN poetry config virtualenvs.create false \
    && poetry install --without dev --no-interaction --no-ansi

# Copy application code
COPY app/ ./app/
COPY ui/ ./ui/
COPY seed/ ./seed/
COPY run.py ./

# Expose ports
EXPOSE 8000 7860

# Start the application
CMD ["python", "run.py"]