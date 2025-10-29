# AI Agent Orchestration System

A production-ready backend system for orchestrating multiple AI agents to process text through summarization, sentiment analysis, and entity extraction. Built with FastAPI, PostgreSQL, and OpenAI.

## Features

- 🤖 **Multi-Agent Processing**: Orchestrate summarizer, sentiment analyzer, and entity extractor agents
- 🔄 **Flexible Execution Modes**: Sequential or parallel agent execution
- 🔗 **Webhook Support**: Asynchronous processing with secure webhook callbacks
- 🔒 **Security**: HMAC-SHA256 signature verification for webhook payloads
- 📊 **Comprehensive Logging**: Structured JSON logging with correlation IDs
- 🏥 **Health Monitoring**: Built-in health checks for database and OpenAI API
- 🔁 **Retry Logic**: Automatic retry mechanism for failed webhook deliveries
- 📈 **Result Tracking**: Full audit trail of all processing requests and agent results

## Tech Stack

- **Framework**: FastAPI (Python 3.12+)
- **Database**: PostgreSQL with SQLAlchemy (async)
- **AI**: OpenAI API (GPT-4o-mini)
- **Task Queue**: FastAPI BackgroundTasks
- **Migrations**: Alembic
- **Package Manager**: uv
- **Containerization**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Python 3.12 or higher
- PostgreSQL database
- OpenAI API key
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd Backend
```

2. **Install dependencies**
```bash
uv sync
```

3. **Set up environment variables**

Create a `.env` file in the root directory:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
OPENAI_API_KEY=sk-your-openai-api-key
LOG_LEVEL=INFO
DEBUG=false
```

4. **Run database migrations**

```bash
uv run alembic upgrade head
```

5. **Start the server**

```bash
uv run uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`

## Docker Setup

### Using Docker Compose

1. **Update environment variables** in `docker-compose.yml`

2. **Start services**
```bash
docker-compose up -d
```

This will start:
- PostgreSQL database
- FastAPI application

### Using Docker

```bash
docker build -t ai-agent-orch .
docker run -p 8000:8000 --env-file .env ai-agent-orch
```

## API Documentation

Once the server is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

For detailed API instructions for frontend integration, see [API.md](./API.md)

## Project Structure

```
backend/
├── src/backend/
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Configuration management
│   ├── database.py             # Database connection
│   ├── models.py               # SQLAlchemy ORM models
│   ├── schemas.py              # Pydantic schemas
│   ├── agents/                 # AI agent implementations
│   │   ├── base_agent.py
│   │   ├── summarizer.py
│   │   ├── sentiment.py
│   │   ├── entity_extractor.py
│   │   └── orchestrator.py
│   ├── api/                    # API routes
│   │   ├── routes.py           # REST endpoints
│   │   ├── webhooks.py        # Webhook endpoints
│   │   └── dependencies.py    # FastAPI dependencies
│   ├── services/               # Business logic
│   │   ├── processing_service.py
│   │   └── webhook_service.py
│   └── utils/                  # Utilities
│       ├── logger.py
│       ├── exceptions.py
│       └── background_tasks.py
├── alembic/                    # Database migrations
├── scripts/                    # Utility scripts
│   └── smoke_test_api.py      # API test script
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Configuration

All configuration is managed through environment variables. See `.env.example` for all available options:

- `DATABASE_URL`: PostgreSQL connection string
- `OPENAI_API_KEY`: OpenAI API key (required)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `WEBHOOK_TIMEOUT`: Webhook request timeout in seconds (default: 30)
- `WEBHOOK_MAX_RETRIES`: Maximum webhook retry attempts (default: 3)
- `MAX_TEXT_LENGTH`: Maximum text length for processing (default: 10000)
- `CORS_ORIGINS`: Allowed CORS origins (JSON array or comma-separated)

## Usage Examples

### Basic Text Processing

```bash
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your text here with at least 10 characters...",
    "orchestration_mode": "sequential"
  }'
```

### With Webhook

```bash
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your text here...",
    "orchestration_mode": "parallel",
    "webhook_url": "https://your-app.com/webhook/callback",
    "webhook_secret": "your-secret-key"
  }'
```

### Get Results

```bash
curl http://localhost:8000/api/v1/results/{request_id}
```

## Testing

Run the API test script:

```bash
uv run python scripts/smoke_test_api.py
```

## Database Migrations

### Create a new migration

```bash
uv run alembic revision --autogenerate -m "description"
```

### Apply migrations

```bash
uv run alembic upgrade head
```

### Rollback

```bash
uv run alembic downgrade -1
```

## Development

### Adding Dependencies

Using `uv`:
```bash
uv add package-name
```

### Running in Development Mode

```bash
DEBUG=true uv run uvicorn src.backend.main:app --reload
```

## Production Deployment

1. Set `DEBUG=false` in environment variables
2. Configure proper `CORS_ORIGINS` for your domain
3. Use a production-grade database (managed PostgreSQL recommended)
4. Set up proper logging aggregation
5. Consider using a proper task queue (Celery) for high-volume scenarios
6. Enable HTTPS
7. Set up monitoring and alerting

## API Endpoints

### Core Endpoints

- `POST /api/v1/process` - Submit text for processing
- `GET /api/v1/results/{request_id}` - Get processing results
- `GET /api/v1/results` - List all results (paginated)
- `GET /api/v1/webhook-logs/{request_id}` - Get webhook delivery logs
- `POST /api/v1/webhook/retry/{request_id}` - Manually retry webhook
- `GET /api/v1/health` - Health check

### Webhook Endpoints

- `POST /webhook/receive` - Receive processing requests via webhook
- `POST /webhook/callback/test` - Test webhook callback endpoint

For detailed API documentation, see [API.md](./API.md)

## Error Handling

The API returns structured error responses:

```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "request_id": "optional-request-id"
}
```

## Webhook Security

Webhooks are secured using HMAC-SHA256 signatures. The signature is sent in the `X-Webhook-Signature` header. Verify it using your `webhook_secret`:

```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## Background Tasks

The system uses FastAPI BackgroundTasks for asynchronous processing:

- Text processing runs in the background
- Webhook delivery retries happen automatically
- Old logs are cleaned up daily (configurable)

## Monitoring

- Health endpoint: `/api/v1/health`
- Structured JSON logs with correlation IDs
- Webhook delivery tracking in database

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]

## Support

For issues and questions, please open an issue in the repository.

---

**Built with ❤️ using FastAPI and OpenAI**

