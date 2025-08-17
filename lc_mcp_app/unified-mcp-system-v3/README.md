# 🚀 Unified MCP System

![CI](https://github.com/grapheneaffiliate/unified-mcp-system-v3/actions/workflows/ci.yml/badge.svg)

A production-ready, comprehensive Model Context Protocol (MCP) system that combines:
- **MCP Agent Server**: Advanced MCP server with enterprise security and observability
- **LC MCP App**: OpenAI-compatible intermediary for seamless LangChain integration

## 🏗️ Architecture Overview

```
unified-mcp-system/
├── mcp_agent/              # MCP Server Components
│   ├── server.py           # Core MCP server implementation
│   ├── database/           # SQLModel database operations
│   ├── security/           # Auth, rate limiting, sandboxing
│   └── observability/      # Logging, metrics, monitoring
├── lc_mcp_app/            # OpenAI-Compatible Intermediary
│   ├── server.py           # FastAPI OpenAI-compatible API
│   ├── clients/            # MCP client with connection pooling
│   ├── middleware/         # Auth, rate limiting, metrics
│   └── tools/              # Dynamic tool registry
├── tests/                  # Comprehensive test suite
├── docker-compose.yml      # Multi-service deployment
└── .github/workflows/      # CI/CD pipelines
```

## ✨ Key Features

### 🔒 **Enterprise Security**
- Bearer token authentication
- Rate limiting with Redis backend
- Input validation and sanitization
- Secure sandboxed execution environment

### 📊 **Production Observability**
- Structured logging with correlation IDs
- Prometheus metrics and health checks
- Request tracing and performance monitoring
- Comprehensive error handling

### ⚡ **High Performance**
- Async architecture throughout
- Connection pooling for MCP clients
- Streaming API support
- Back-pressure handling

### 🔌 **OpenAI Compatibility**
- Full OpenAI Chat Completions API
- Streaming and non-streaming responses
- Function calling support
- Model selection and routing

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker (optional)
- Redis (for rate limiting)

### Installation

```bash
# Clone the repository
git clone https://github.com/grapheneaffiliate/unified-mcp-system-v3.git
cd unified-mcp-system-v3

# Install dependencies
pip install -e ".[dev]"

# Set up environment
cp .env.example .env
# Edit .env with your configuration
```

### Running the System

#### Option 1: Docker Compose (Recommended)
```bash
# Start all services
docker-compose up --build

# MCP Server: http://localhost:8000
# LC MCP App: http://localhost:8001
# Prometheus: http://localhost:9090
# Redis: localhost:6379
```

#### Option 2: Manual Setup
```bash
# Terminal 1: Start MCP Server
make mcp-server

# Terminal 2: Start LC MCP App
make lc-app

# Terminal 3: Start Redis (if not using Docker)
redis-server
```

## 🛠️ Development

### Development Commands
```bash
# Install development dependencies
make install-dev

# Run tests
make test

# Run linting
make lint

# Run type checking
make type-check

# Format code
make format

# Run all checks
make check-all
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=lc_mcp_app --cov=mcp_agent

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not slow"    # Skip slow tests
```

## 📡 API Usage

### MCP Server (Port 8000)
Direct MCP protocol communication:
```python
from mcp import ClientSession
from mcp.client.stdio import stdio_client

# Connect to MCP server
async with stdio_client() as (read, write):
    async with ClientSession(read, write) as session:
        # List available tools
        tools = await session.list_tools()
        
        # Call a tool
        result = await session.call_tool("execute_command", {
            "command": "ls -la"
        })
```

### LC MCP App (Port 8001)
OpenAI-compatible API:
```python
import openai

# Configure client
client = openai.OpenAI(
    base_url="http://localhost:8001/v1",
    api_key="your-api-key"
)

# Chat completion
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "List files in current directory"}
    ],
    tools=[
        {
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "Execute shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"}
                    }
                }
            }
        }
    ]
)
```

### Streaming Support
```python
# Streaming chat completion
stream = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## 🔧 Configuration

### Environment Variables
```bash
# MCP Server Configuration
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
MCP_LOG_LEVEL=INFO
MCP_DATABASE_URL=sqlite:///./mcp_agent.db

# LC MCP App Configuration
LC_APP_HOST=0.0.0.0
LC_APP_PORT=8001
LC_APP_LOG_LEVEL=INFO
OPENAI_API_KEY=your-openai-api-key

# Security
AUTH_SECRET_KEY=your-secret-key
RATE_LIMIT_ENABLED=true
REDIS_URL=redis://localhost:6379

# Observability
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=9090
STRUCTURED_LOGGING=true
```

## 🐳 Docker Deployment

### Production Deployment
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  mcp-server:
    build: .
    command: ["python", "-m", "mcp_agent.server"]
    environment:
      - MCP_SERVER_PORT=8000
      - MCP_LOG_LEVEL=INFO
    ports:
      - "8000:8000"
    
  lc-mcp-app:
    build: .
    command: ["python", "-m", "lc_mcp_app.server"]
    environment:
      - LC_APP_PORT=8001
      - LC_APP_LOG_LEVEL=INFO
    ports:
      - "8001:8001"
    depends_on:
      - mcp-server
      - redis
    
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

## 🔍 Monitoring

### Health Checks
- **MCP Server**: `GET http://localhost:8000/health`
- **LC MCP App**: `GET http://localhost:8001/health`

### Metrics
- **Prometheus**: `http://localhost:9090`
- **Custom metrics**: Request latency, error rates, tool usage

### Logging
- Structured JSON logging
- Correlation IDs for request tracing
- Configurable log levels
- Integration with external log aggregators

## 🛡️ Security Features

### Authentication
- Bearer token authentication
- JWT token support
- API key validation
- Role-based access control

### Rate Limiting
- Per-user rate limiting
- Global rate limiting
- Redis-backed counters
- Configurable limits

### Sandboxing
- Secure command execution
- File system access controls
- Network restrictions
- Resource limits

## 🧪 Testing

### Test Structure
```
tests/
├── test_health.py          # Health check tests
├── test_openai_api.py      # OpenAI API compatibility tests
└── mcp_server/
    └── test_server.py      # MCP server tests
```

### Running Tests
```bash
# All tests
make test

# Specific test files
pytest tests/test_health.py
pytest tests/mcp_server/test_server.py

# With coverage
make test-coverage
```

## 📚 Documentation

### API Documentation
- **OpenAI API**: Available at `http://localhost:8001/docs`
- **MCP Server**: Available at `http://localhost:8000/docs`

### Examples
See the `examples/` directory for:
- Basic usage examples
- Integration patterns
- Custom tool development
- Deployment configurations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `make test`
5. Run linting: `make lint`
6. Commit changes: `git commit -m 'Add amazing feature'`
7. Push to branch: `git push origin feature/amazing-feature`
8. Open a Pull Request

### Development Setup
```bash
# Install development dependencies
make install-dev

# Set up pre-commit hooks
pre-commit install

# Run all checks before committing
make check-all
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) by Anthropic
- [LangChain](https://langchain.com/) for LLM integration
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [OpenAI](https://openai.com/) for API compatibility standards

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/grapheneaffiliate/unified-mcp-system-v3/issues)
- **Discussions**: [GitHub Discussions](https://github.com/grapheneaffiliate/unified-mcp-system-v3/discussions)
- **Documentation**: [Project Wiki](https://github.com/grapheneaffiliate/unified-mcp-system-v3/wiki)

---

**Built with ❤️ for the MCP community**
