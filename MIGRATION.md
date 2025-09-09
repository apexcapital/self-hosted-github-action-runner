# Migration Guide: v1.0 → v2.0 Orchestrator

## Overview of Changes

This document outlines the key differences between your current static runner setup and the new orchestrator-based system.

## Architecture Comparison

### Current System (v1.0)

```text
GitHub Repository
       ↓
   Static Runner Container
   (Always running, manual scaling)
       ↓
   Docker-in-Docker
```

### New System (v2.0)

```text
GitHub Repository/Org
       ↓
   Orchestrator Container
   (Monitors queue, auto-scales)
       ↓
   Dynamic Runner Containers
   (Created/destroyed on demand)
       ↓
   Docker-in-Docker
```

## Key Improvements

| Feature | v1.0 | v2.0 |
|---------|------|------|
| **Scaling** | Manual | Automatic |
| **Resource Usage** | Always consumes resources | Scales to zero when idle |
| **Queue Monitoring** | None | Continuous GitHub API polling |
| **Runner Lifecycle** | Long-lived | Ephemeral |
| **Management Interface** | Docker commands only | REST API + Web UI |
| **Monitoring** | Basic Docker logs | Prometheus metrics + structured logging |
| **Token Management** | Manual renewal | Automatic token refresh |
| **Multi-repo Support** | One repo per container | Organization-wide or multi-repo |

## Configuration Migration

### v1.0 Configuration (.env)

```bash
RUNNER_VERSION=2.325.0
RUNNER_NAME=my-self-hosted-runner
REPO_URL=https://github.com/owner/repo
RUNNER_TOKEN=github_pat_xxxxx
RUNNER_WORKDIR=_work
```

### v2.0 Configuration (.env.orchestrator)

```bash
# GitHub Configuration
GITHUB_TOKEN=github_pat_xxxxx          # Replaces RUNNER_TOKEN
GITHUB_ORG=your-organization           # NEW: Organization-wide runners
GITHUB_REPO=owner/repo                 # Alternative to ORG

# Scaling Configuration (NEW)
MIN_RUNNERS=2                          # Always maintain this many
MAX_RUNNERS=10                         # Never exceed this many
SCALE_UP_THRESHOLD=3                   # Scale up when queue >= this
SCALE_DOWN_THRESHOLD=1                 # Scale down when queue <= this
IDLE_TIMEOUT=300                       # Seconds before terminating idle runners

# Monitoring Configuration (NEW)
POLL_INTERVAL=30                       # Seconds between API polls
LOG_LEVEL=INFO                         # Logging verbosity
STRUCTURED_LOGGING=true                # JSON logging format

# Docker Configuration
RUNNER_IMAGE=ghcr.io/apexcapital/runner:latest
RUNNER_VERSION=2.325.0                 # Same as before
RUNNER_NETWORK=runner-network          # NEW: Dedicated network
```

## Deployment Comparison

### v1.0 Deployment

```bash
# Single container deployment
docker run -d \
  --name my-self-hosted-runner \
  --restart unless-stopped \
  -e REPO_URL="https://github.com/owner/repo" \
  -e RUNNER_TOKEN="github_pat_xxxxx" \
  -e RUNNER_NAME="my-runner" \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v ~/runner-work:/actions-runner/_work \
  ghcr.io/velvet-labs-llc/runner:latest
```

### v2.0 Deployment

```bash
# Orchestrator-based deployment
cp .env.orchestrator.example .env.orchestrator
# Edit .env.orchestrator with your settings
docker-compose -f docker-compose.orchestrator.yml up -d --build

# Or use the setup script
./setup-orchestrator.sh
```

## Operational Differences

### v1.0 Operations

```bash
# View logs
docker logs -f my-self-hosted-runner

# Restart runner
docker restart my-self-hosted-runner

# Scale up (manual)
docker run -d --name another-runner ...

# Check status
docker ps | grep runner
```

### v2.0 Operations

```bash
# View orchestrator logs
docker logs -f github-runner-orchestrator

# View specific runner logs
curl http://localhost:8080/api/v1/runners/{runner_id}/logs

# Manual scaling
curl -X POST http://localhost:8080/api/v1/runners/scale-up
curl -X POST http://localhost:8080/api/v1/runners/scale-down

# Check status
curl http://localhost:8080/api/v1/status | jq

# Web interface
open http://localhost:8080/docs
```

## GitHub Workflow Changes

### v1.0 Workflow Labels

```yaml
runs-on: self-hosted
# or
runs-on: [self-hosted, docker-dind, linux, x64]
```

### v2.0 Workflow Labels

```yaml
runs-on: [self-hosted, orchestrated]
# or for more specific targeting
runs-on: [self-hosted, orchestrated, docker-dind, linux, x64]
```

## Token Management

### v1.0 Token Management

- **Token Type**: Runner registration token (short-lived, ~1 hour)
- **Renewal**: Manual regeneration required
- **Scope**: Repository-specific
- **Management**: GitHub UI → Settings → Actions → Runners

### v2.0 Token Management

- **Token Type**: Personal Access Token (long-lived, configurable)
- **Renewal**: Automatic refresh by orchestrator
- **Scope**: Organization or repository level
- **Management**: GitHub UI → Settings → Developer settings → Personal access tokens

### Creating PAT for v2.0

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Select resource owner (your account or organization)
3. Set expiration (recommend 1 year)
4. Select repository access:
   - For single repo: "Selected repositories" → choose your repo
   - For organization: "All repositories" under the organization
5. Required permissions:
   - **Repository permissions**:
     - `Actions`: Read and Write
     - `Metadata`: Read
   - **Organization permissions** (if using GITHUB_ORG):
     - `Self-hosted runners`: Write

## Monitoring & Observability

### v1.0 Monitoring

- Docker container logs
- Basic health checks
- Manual status checking

### v2.0 Monitoring

- **REST API**: Full status and control interface
- **Prometheus Metrics**: Queue length, runner counts, scaling events
- **Structured Logging**: JSON logs with correlation IDs
- **Health Checks**: Automatic container health monitoring
- **Web Dashboard**: Interactive API documentation and testing

## Troubleshooting Guide

### Common Migration Issues

1. **GitHub Token Permissions**

   ```bash
   # Test token permissions
   curl -H "Authorization: token YOUR_PAT" \
        https://api.github.com/repos/OWNER/REPO/actions/runners
   ```

2. **Network Connectivity**

   ```bash
   # Test from orchestrator container
   docker exec -it github-runner-orchestrator \
     curl -H "Authorization: token YOUR_PAT" \
          https://api.github.com/user
   ```

3. **Runner Registration Issues**

   ```bash
   # Check orchestrator logs
   docker logs github-runner-orchestrator | grep -i "registration\|token\|error"
   
   # Check specific runner logs
   docker logs $(docker ps -q --filter label=managed-by=runner-orchestrator)
   ```

4. **Scaling Not Working**

   ```bash
   # Check queue monitoring
   curl http://localhost:8080/api/v1/status | jq '.queue'
   
   # Manually trigger scaling
   curl -X POST http://localhost:8080/api/v1/runners/scale-up
   ```

## Performance Comparison

### v1.0 Performance

- **Startup Time**: Fast (container already running)
- **Resource Usage**: Constant (always consuming resources)
- **Scaling Latency**: Manual intervention required
- **Cost Efficiency**: Poor (resources wasted during idle periods)

### v2.0 Performance

- **Startup Time**: ~30-60 seconds (container creation + runner registration)
- **Resource Usage**: Dynamic (scales to zero when idle)
- **Scaling Latency**: 30-90 seconds (automatic based on queue)
- **Cost Efficiency**: Excellent (only uses resources when needed)

## Rollback Plan

If you need to rollback to v1.0:

```bash
# Stop orchestrator
docker-compose -f docker-compose.orchestrator.yml down

# Remove orchestrator containers and networks
docker system prune -f

# Restart old runner
docker run -d \
  --name my-self-hosted-runner \
  --restart unless-stopped \
  --env-file .env \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  ghcr.io/velvet-labs-llc/runner:latest
```

## Migration Checklist

- [ ] Create GitHub Personal Access Token with appropriate permissions
- [ ] Copy and configure `.env.orchestrator` file
- [ ] Test GitHub API connectivity with new token
- [ ] Deploy orchestrator system: `./setup-orchestrator.sh`
- [ ] Verify orchestrator is running: `curl http://localhost:8080/health`
- [ ] Check that runners are being created: `curl http://localhost:8080/api/v1/runners`
- [ ] Update workflow files to use `orchestrated` label
- [ ] Test workflow execution with new system
- [ ] Monitor scaling behavior during normal usage
- [ ] Set up Prometheus monitoring (optional)
- [ ] Stop and remove old v1.0 runner containers
- [ ] Update documentation and team processes

## Benefits Realized

After migration, you should see:

1. **Automatic Scaling**: Runners appear when needed, disappear when idle
2. **Cost Reduction**: No more idle resource consumption
3. **Better Reliability**: Failed runners are automatically replaced
4. **Improved Visibility**: Real-time metrics and status monitoring
5. **Easier Management**: Web-based interface instead of command-line only
6. **Organization Support**: Single orchestrator can serve multiple repositories
