# Official Playwright Python image (pre-configured with Chromium, SwiftShader software WebGL, and Linux dependencies)
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    MCP_TRANSPORT=sse \
    MCP_HOST=0.0.0.0 \
    PORT=8000

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Install the onshape-mcp package
RUN pip install --no-cache-dir .

EXPOSE 8000

# Launch MCP in SSE transport mode
CMD ["python3", "-m", "onshape_mcp.server", "--transport", "sse"]
