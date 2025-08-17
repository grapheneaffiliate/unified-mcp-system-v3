# Multi-stage build for security and efficiency
FROM python:3.11-slim as builder

# Set build arguments
ARG PYTHONDONTWRITEBYTECODE=1
ARG PYTHONUNBUFFERED=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e .

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd -r -g 10001 mcpuser && \
    useradd -r -g mcpuser -u 10001 -m -d /app mcpuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=mcpuser:mcpuser lc_mcp_app/ ./lc_mcp_app/
COPY --chown=mcpuser:mcpuser mcp_agent/ ./mcp_agent/
COPY --chown=mcpuser:mcpuser tests/ ./tests/

# Create necessary directories
RUN mkdir -p /app/data /app/logs && \
    chown -R mcpuser:mcpuser /app

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || curl -f http://localhost:8001/health || exit 1

# Switch to non-root user
USER mcpuser

# Expose ports
EXPOSE 8000 8001

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "lc_mcp_app.server"]
