# GitHub Actions Runner Orchestrator 2.0

## Enhanced Dynamic Runner Management System

This system provides intelligent, dynamic scaling of ephemeral GitHub Actions runners based on workload demand. It replaces static, single-runner setups with a sophisticated orchestrator that automatically manages runner lifecycle.

## 🚀 Key Features

### 🎯 **Dynamic Scaling**

- **Intelligent Queue Monitoring**: Continuously monitors GitHub Actions queue length
- **Auto-scaling**: Automatically provisions/deprovisions runners based on demand
- **Configurable Thresholds**: Customizable scale-up/down triggers
- **Pool Management**: Maintains a minimum pool of always-available runners

### 🐳 **Container Orchestration**

- **Ephemeral Runners**: Runners are created on-demand and destroyed when idle
- **Docker-in-Docker**: Full Docker support for containerized workflows
- **Network Isolation**: Dedicated Docker networks for security
- **Resource Management**: Automatic cleanup of containers and volumes

### 📊 **Monitoring & Observability**

- **REST API**: Full management API for status, metrics, and control
- **Prometheus Metrics**: Built-in metrics collection for monitoring
- **Structured Logging**: Comprehensive logging with correlation IDs
- **Health Checks**: Container health monitoring and self-healing

### 🔐 **Security & Reliability**

- **GitHub PAT Integration**: Uses Personal Access Token for API access
- **Graceful Shutdown**: Proper cleanup and runner unregistration
- **Error Recovery**: Automatic retry logic and error handling
- **Signal Handling**: Proper process management and termination

## 🏗️ Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub API Integration                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Orchestrator Container                      │
│  ┌───────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │  Queue Monitor│  │ Runner Pool  │  │ Metrics & Scaling   │  │
│  │               │  │  Manager     │  │                     │  │
│  └───────────────┘  └──────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Daemon / Docker API                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │  Runner-1    │ │  Runner-2    │ │  Runner-N    │
        │ (Ephemeral)  │ │ (Ephemeral)  │ │ (Ephemeral)  │
        └──────────────┘ └──────────────┘ └──────────────┘
```

## 🚦 Quick Start

### 1. Prerequisites

- Docker and Docker Compose
- GitHub Personal Access Token with appropriate permissions
- Access to GitHub repository/organization

### 2. Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd self-hosted-github-action-runner

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# Build and start the orchestrator
# (Optional) Build the custom runner image used by the orchestrator and then start services
# Build using the repository root as the build context so files like `daemon.json`
# (located at the repo root) are available to the Dockerfile. The Dockerfile is
# taken from `runner-image/Dockerfile`.
docker build -t apex-runner:local -f runner-image/Dockerfile . || true
docker compose up -d --build
```

### 3. Configuration

Edit `.env`:

```bash
# GitHub Configuration - REQUIRED
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_ORG=your-organization  # OR use GITHUB_REPO
GITHUB_REPO=owner/repo-name   # Alternative to ORG

# Scaling Configuration
MIN_RUNNERS=2          # Always maintain this many runners
MAX_RUNNERS=10         # Never exceed this many runners
SCALE_UP_THRESHOLD=3   # Scale up when queue length >= this
SCALE_DOWN_THRESHOLD=1 # Scale down when queue length <= this
```

### 4. Monitor

```bash
# View orchestrator logs
docker logs -f orchestrator

# Check status via API
curl http://localhost:8080/api/v1/status

# View Prometheus metrics
curl http://localhost:8080/api/v1/metrics

# Access web dashboard (if configured)
open http://localhost:8080/docs
```

## 📖 API Documentation

### Status Endpoint

```bash
GET /api/v1/status
# Returns orchestrator status, runner counts, queue info
```

### Runners Management

```bash
GET /api/v1/runners
# List all runners (Docker + GitHub)

POST /api/v1/runners/scale-up
# Manually trigger scale up

POST /api/v1/runners/scale-down
# Manually trigger scale down

DELETE /api/v1/runners/{runner_id}
# Remove a specific runner

GET /api/v1/runners/{runner_id}/logs
# Get logs from a specific runner
```

### Metrics

```bash
GET /api/v1/metrics
# Prometheus-style metrics
```

## ⚙️ Configuration Options

### GitHub Configuration

- `GITHUB_TOKEN`: Personal Access Token (required)
- `GITHUB_ORG`: Organization name (for org-level runners)
- `GITHUB_REPO`: Repository in format "owner/repo" (alternative to ORG)

### Scaling Configuration

- `MIN_RUNNERS`: Minimum runners to maintain (default: 2)
- `MAX_RUNNERS`: Maximum runners allowed (default: 10)
- `SCALE_UP_THRESHOLD`: Queue length to trigger scale up (default: 3)
- `SCALE_DOWN_THRESHOLD`: Queue length to trigger scale down (default: 1)
- `IDLE_TIMEOUT`: Seconds before idle runners are terminated (default: 300)

### Monitoring Configuration

- `POLL_INTERVAL`: Seconds between GitHub API polls (default: 30)
- `LOG_LEVEL`: Logging level (default: INFO)
- `STRUCTURED_LOGGING`: Enable structured JSON logging (default: true)

## 🎛️ Advanced Features

### Prometheus Monitoring

The orchestrator includes built-in Prometheus metrics:

```yaml
# prometheus.yml included in the setup
- job_name: 'orchestrator'
  static_configs:
    - targets: ['orchestrator:8080']
  metrics_path: '/api/v1/metrics'
```

### Custom Runner Labels

Configure custom labels for your runners:

```yaml
environment:
  ORCHESTRATOR_RUNNER_LABELS: "docker-dind,linux,self-hosted,my-custom-label"

### Customizing the Runner Image

This project now builds and uses a local runner image by default (`apex-runner:local`).
You can customize the runner image by editing `runner-image/Dockerfile` and adding
any packages or tools your workflows need. The `setup-orchestrator.sh` script will
attempt to build `apex-runner:local` from `runner-image/` during setup. If you prefer
to use a remote image, set `ORCHESTRATOR_RUNNER_IMAGE` in `.env` to the desired
image (e.g. `ghcr.io/yourorg/runner:tag`).
```

### Distributed Setup

For multiple orchestrator instances, enable Redis coordination:

```yaml
environment:
  REDIS_URL: "redis://redis:6379/0"
```

## 🔧 Troubleshooting

### Common Issues

1. **Orchestrator won't start**

   ```bash
   # Check logs
   docker logs orchestrator
   
   # Verify GitHub token permissions
   curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
   ```

2. **Runners not registering**

   ```bash
   # Check runner logs
   docker logs $(docker ps -q --filter label=managed-by=runner-orchestrator)
   
   # Verify network connectivity
   docker exec -it orchestrator ping github.com
   ```

3. **Scaling not working**

   ```bash
   # Check queue monitoring
   curl http://localhost:8080/api/v1/status | jq '.queue'
   
   # Manually trigger scaling
   curl -X POST http://localhost:8080/api/v1/runners/scale-up
   ```

### Debug Mode

Enable debug logging:

```yaml
environment:
  ORCHESTRATOR_LOG_LEVEL: DEBUG
```

## 🛠️ Development

### Running Locally

```bash
cd orchestrator
pip install -r requirements.txt
python main.py
```

### Testing

```bash
# Test GitHub API connectivity
python -c "
from src.github_client import GitHubClient
client = GitHubClient('your-token', org='your-org')
import asyncio
print(asyncio.run(client.get_runners()))
"
```

## 📈 Performance Tuning

### Recommended Settings

#### Small Team (1-5 developers)

```yaml
MIN_RUNNERS: 1
MAX_RUNNERS: 5
SCALE_UP_THRESHOLD: 2
POLL_INTERVAL: 60
```

#### Medium Team (5-20 developers)

```yaml
MIN_RUNNERS: 2
MAX_RUNNERS: 10
SCALE_UP_THRESHOLD: 3
POLL_INTERVAL: 30
```

#### Large Team (20+ developers)

```yaml
MIN_RUNNERS: 5
MAX_RUNNERS: 20
SCALE_UP_THRESHOLD: 5
POLL_INTERVAL: 15
```

## 🆕 Migration from v1.0

### Key Differences

1. **Single Container → Orchestrator + Ephemeral Runners**
2. **Manual Scaling → Automatic Scaling**
3. **Static Configuration → Dynamic Management**
4. **Simple Entrypoint → Full API & Monitoring**

### Migration Steps

1. **Backup existing setup**
2. **Stop old runners**: `docker stop my-self-hosted-runner`
3. **Deploy orchestrator**: Follow Quick Start guide
4. **Update workflow labels**: Use `self-hosted,orchestrated` labels
5. **Monitor and tune**: Adjust scaling parameters

## 🔄 Migration from v1.0

This system completely replaces the previous static runner setup. If you were using the v1.0 system:

### What Changed

- **Static → Dynamic**: Runners are now ephemeral and auto-scale
- **Single Runner → Pool**: Maintains multiple runners automatically
- **Manual → Automated**: No more manual runner registration
- **Limited → Scalable**: Scales from 0 to configurable maximum

### Migration Process

1. **Stop old runners**: `docker compose down` (if using old setup)
2. **Update configuration**: Use new `.env` format (see Configuration section)
3. **Deploy orchestrator**: `docker compose up -d --build`
4. **Update workflows**: No changes needed - existing workflows work automatically

### File Changes

- `docker compose.yml` → Now orchestrator-only
- `.env.example` → Simplified environment variables
- `Dockerfile` → Now builds orchestrator image
- `setup-orchestrator.sh` → Updated for new file structure

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
