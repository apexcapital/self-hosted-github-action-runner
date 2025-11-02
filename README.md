# Self-Hosted GitHub Actions Runner (SHGHAR) Orchestrator 2.0

**Intelligent, Auto-Scaling GitHub Actions Runner Management**

A production-ready orchestrator that dynamically manages ephemeral GitHub Actions self-hosted runners based on workload demand. Automatically scales runners up and down, maintains minimum capacity, and handles runner lifecycle with comprehensive monitoring and safety mechanisms.
Currently, supports both repository-level and organization-level runners and provides browser dependencies for workflows requiring web browser testing, i.e. Playwright, Puppeteer, Selenium, etc.
---

## 📋 Table of Contents

- [Overview](#-overview)
- [How It Works](#-how-it-works)
- [Architecture](#-architecture)
- [Key Features](#-key-features)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Orchestrator Components](#-orchestrator-components)
- [Scaling Logic](#-scaling-logic)
- [API Documentation](#-api-documentation)
- [Monitoring & Observability](#-monitoring--observability)
- [Troubleshooting](#-troubleshooting)
- [Advanced Usage](#-advanced-usage)

---

## 🎯 Overview

This orchestrator solves the problem of managing self-hosted GitHub Actions runners at scale. Instead of manually managing static runners that waste resources when idle or become bottlenecks during peak usage, this system:

- **Automatically creates runners** when GitHub Actions jobs are queued
- **Maintains a minimum pool** of always-ready runners for instant job pickup
- **Scales down during idle periods** to conserve resources
- **Replaces dead runners** automatically within 60 seconds
- **Monitors runner health** continuously
- **Provides observability** through REST API, metrics, and structured logging

### Use Cases

- **Development Teams**: Eliminate queue wait times during peak hours
- **CI/CD Pipelines**: Ensure runners are always available when needed
- **Cost Optimization**: Only run the runners you need, when you need them
- **High Availability**: Automatic replacement of failed runners
- **Multi-Project**: Single orchestrator can manage runners for repos or entire organizations

---

## 🔍 How It Works

### The Problem This Solves

Traditional self-hosted runner setups have several issues:

1. **Static capacity**: Fixed number of runners, regardless of demand
2. **Resource waste**: Runners consume resources even when idle
3. **Manual management**: Dead runners require manual intervention
4. **Queue bottlenecks**: Not enough runners during peak times
5. **No visibility**: Hard to know runner status and capacity

### The Solution

This orchestrator uses a **dynamic, event-driven approach**:

```
┌─────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Background Tasks (Running Continuously)                 │   │
│  │                                                          │   │
│  │  1. Queue Monitor        → Polls GitHub every 30s        │   │
│  │  2. Minimum Maintainer   → Ensures min runners every 60s │   │
│  │  3. Runner Manager       → Tracks health every 30s       │   │
│  │  4. Sync Task            → Cleans orphans every 2min     │   │
│  │  5. Cleanup Task         → Removes dead containers       │   │
│  │  6. Utilization Monitor  → Checks usage every 60s        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Decision Flow:                                                 │
│  • Low queue + low utilization → Scale down                     │
│  • High queue OR high utilization → Scale up                    │
│  • Below minimum online runners → Create runners                │
│  • Dead/offline runner detected → Replace within 60s            │
└─────────────────────────────────────────────────────────────────┘
```

### Lifecycle of a Runner

1. **Creation**
   - Orchestrator requests registration token from GitHub API
   - Creates Docker container with runner software
   - Runner registers with GitHub (takes ~30-60 seconds)
   - Runner appears as "online" in GitHub

2. **Active State**
   - Runner polls GitHub for available jobs
   - Picks up jobs matching its labels
   - Executes workflow steps
   - Reports results back to GitHub

3. **Idle State**
   - No jobs assigned for configured `IDLE_TIMEOUT`
   - Orchestrator may scale down if above minimum
   - Removes container gracefully (runner deregisters from GitHub)

4. **Failure/Death**
   - Runner crashes or becomes unresponsive
   - Shows as "offline" in GitHub within 1-2 minutes
   - Minimum maintainer detects missing online runner
   - Creates replacement within 60 seconds

---

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         GitHub Cloud                            │
│  • Actions API (queue monitoring)                               │
│  • Runners API (registration, status)                           │
│  • Webhooks (optional future enhancement)                       │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ GitHub API Calls
                              │ (HTTPS)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator Container                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  FastAPI Web Server (Port 8080)                          │   │
│  │  • REST API endpoints                                    │   │
│  │  • Health checks                                         │   │
│  │  • Prometheus metrics                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Orchestrator Core                                       │   │
│  │  • GitHubClient (API communication)                      │   │
│  │  • DockerClient (container management)                   │   │
│  │  • Six concurrent background tasks                       │   │
│  │  • Metrics tracking and circuit breaker                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Docker API
                              │ (Unix Socket)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Docker Daemon                             │
│  • Container lifecycle management                               │
│  • Volume management                                            │
│  • Network isolation                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Runner 1    │      │  Runner 2    │      │  Runner N    │
│              │      │              │      │              │
│ orchestrated-│      │ orchestrated-│      │ orchestrated-│
│ abc12345     │      │ def67890     │      │ ghi24680     │
│              │      │              │      │              │
│ Status: busy │      │ Status: idle │      │ Status: idle │
└──────────────┘      └──────────────┘      └──────────────┘
```

### Data Flow

1. **Startup Flow**
   ```
   main.py starts → Orchestrator.__init__() → 
   validate GitHub token → start background tasks → 
   _scale_to_minimum() creates initial runners
   ```

2. **Scaling Up Flow**
   ```
   Queue monitor detects 5 jobs queued →
   Checks current capacity (2 online runners) →
   Calculates needed (5 - 2 = 3, but max 2 per scale action) →
   Creates 2 new runners →
   Waits for registration (30-60s) →
   Runners go online and pick up jobs
   ```

3. **Scaling Down Flow**
   ```
   Utilization monitor detects 20% usage →
   Has 5 runners, needs only 2 (minimum) →
   Identifies oldest idle runners →
   Gracefully stops container →
   Runner deregisters from GitHub →
   Volume cleanup
   ```

4. **Dead Runner Replacement Flow**
   ```
   Runner crashes (container stops unexpectedly) →
   Within 60s: _manage_runners() detects missing container →
   Within 120s: _sync_runners() removes orphaned GitHub registration →
   Within 60s: _maintain_minimum_runners() detects online count < min →
   Creates replacement runner →
   New runner registers and goes online
   ```

---

## 🚀 Key Features

### 1. Dynamic Scaling

**Intelligent Queue-Based Scaling**
- Monitors GitHub Actions queue every 30 seconds
- Calculates: `queue_length = queued_jobs + in_progress_jobs - available_runners`
- Scale up when `queue_length >= SCALE_UP_THRESHOLD` (default: 3)
- Scale down when `queue_length <= SCALE_DOWN_THRESHOLD` (default: 1)

**Utilization-Based Scaling**
- Checks runner utilization every 60 seconds
- Scale up if utilization ≥ 80% and jobs are queued
- Scale down if utilization ≤ 20% and above minimum

**Minimum Runner Maintenance** (NEW)
- Continuously ensures minimum online runners (default: 2)
- Counts only runners with status "online" (not offline/dead)
- Replaces failed runners within 60 seconds
- Runs every 60 seconds in background

### 2. Safety Mechanisms

**Circuit Breaker**
- Prevents runaway scaling if max containers reached
- Activates automatically after 5 consecutive failures
- Logs emergency alerts and stops all scaling

**Container Limits**
- Hard limit: never exceed `MAX_RUNNERS` containers
- Soft limit: creates max 2 runners per scaling action
- Cooldown: 60 seconds between scale-up actions

**Failure Handling**
- Retries GitHub API calls 3 times with exponential backoff
- Stops creation attempts after 2 consecutive failures
- Graceful degradation: uses Docker count if GitHub API fails

### 3. Automatic Cleanup

**Dead Container Cleanup**
- Runs every 5 minutes
- Removes exited/stopped containers
- Cleans up associated volumes

**Orphan Removal**
- Runs every 2 minutes
- Removes runners registered in GitHub but not in Docker
- Removes containers running but not registered in GitHub (after 2min grace period)

**Unregistered Container Removal**
- Detects containers that failed to register with GitHub
- Waits 2 minutes for registration to complete
- Removes if still unregistered after grace period

### 4. Observability

**Structured Logging**
- JSON-formatted logs with correlation IDs
- Log levels: DEBUG, INFO, WARNING, ERROR
- Searchable and parseable by log aggregation tools

**REST API**
- `/health` - Health check endpoint
- `/api/v1/status` - Detailed orchestrator status
- `/api/v1/runners` - List all runners
- `/api/v1/metrics` - Prometheus metrics
- `/docs` - Interactive API documentation (Swagger)

**Metrics Tracking**
- Total runners created/destroyed
- Current queue length
- Last scaling action and timestamp
- Circuit breaker status
- Failed scaling attempts

---

## 🚦 Quick Start

### Prerequisites

- **Docker** 20.10+ and **Docker Compose** 2.0+
- **GitHub Personal Access Token** with permissions:
  - Repository: `repo` scope (for repo-level runners)
  - Organization: `admin:org` scope (for org-level runners)
  - Actions: `admin:repo_hook` or `admin:org_hook` for runner management
- **Linux host** (Ubuntu 20.04+ recommended) or macOS with Docker Desktop

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/self-hosted-github-action-runner.git
cd self-hosted-github-action-runner

# 2. Create environment configuration
cat > .env << EOF
# GitHub Configuration
ORCHESTRATOR_GITHUB_TOKEN=ghp_your_token_here
ORCHESTRATOR_GITHUB_REPO=yourusername/your-repo

# Scaling Configuration
ORCHESTRATOR_MIN_RUNNERS=2
ORCHESTRATOR_MAX_RUNNERS=10
ORCHESTRATOR_SCALE_UP_THRESHOLD=3
ORCHESTRATOR_SCALE_DOWN_THRESHOLD=1

# Monitoring
ORCHESTRATOR_POLL_INTERVAL=30
ORCHESTRATOR_LOG_LEVEL=INFO
EOF

# 3. Build the runner image (optional but recommended)
docker build -t shghar:local -f runner-image/Dockerfile .

# 4. Start the orchestrator
docker-compose up -d

# 5. Verify it's running
docker-compose logs -f orchestrator
```

### Expected Startup Behavior

```
✓ Orchestrator container starts
✓ Validates GitHub token (5-10 seconds)
✓ Starts 6 background tasks
✓ Creates 2 runners (MIN_RUNNERS=2)
  - orchestrated-abc12345 (registering...)
  - orchestrated-def67890 (registering...)
✓ Runners register with GitHub (30-60 seconds)
✓ Runners appear as "online" in GitHub
✓ Ready to accept jobs
```

### Verification

```bash
# Check orchestrator status
curl http://localhost:8080/api/v1/status | jq

# Check GitHub runners (via GitHub UI)
# Go to: Settings → Actions → Runners
# Should see: 2 runners with "orchestrated-" prefix, status "Idle"

# Run diagnostic script
./diagnose-runners.sh
```

---

## ⚙️ Configuration

### Environment Variables

All configuration uses the `ORCHESTRATOR_` prefix:

#### GitHub Configuration (Required)

```bash
# Authentication
ORCHESTRATOR_GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
# Your GitHub Personal Access Token

# Target (choose ONE)
ORCHESTRATOR_GITHUB_ORG=my-organization
# For organization-level runners

# OR
ORCHESTRATOR_GITHUB_REPO=owner/repo-name
# For repository-level runners (recommended)
```

#### Scaling Configuration

```bash
ORCHESTRATOR_MIN_RUNNERS=2
# Minimum number of ONLINE runners to maintain at all times
# Default: 2
# Recommendation: Set to expected baseline load

ORCHESTRATOR_MAX_RUNNERS=10
# Maximum number of runners allowed (hard limit)
# Default: 10
# Recommendation: Set based on host resources (2GB RAM per runner)

ORCHESTRATOR_SCALE_UP_THRESHOLD=3
# Queue length that triggers scaling up
# Default: 3
# Recommendation: Lower = more responsive, higher = more cost-effective

ORCHESTRATOR_SCALE_DOWN_THRESHOLD=1
# Queue length that triggers scaling down
# Default: 1
# Recommendation: Keep at 0 or 1 for aggressive scaling down

ORCHESTRATOR_IDLE_TIMEOUT=300
# Seconds before idle runners are terminated
# Default: 300 (5 minutes)
```

#### Runner Configuration

```bash
ORCHESTRATOR_RUNNER_IMAGE=shghar:local
# Docker image for runner containers
# Default: shghar:local (built from runner-image/)

ORCHESTRATOR_RUNNER_LABELS=orchestrated,optimized,self-hosted,linux,docker-dind
# Comma-separated labels for runners
# Default: orchestrated,optimized,self-hosted,linux,docker-dind
# Use in workflows: runs-on: [self-hosted, orchestrated]

ORCHESTRATOR_RUNNER_NETWORK=runner-network
# Docker network name for runners
# Default: runner-network

ORCHESTRATOR_RUNNER_NAME_PREFIX=github-runner
# Prefix for runner container names
# Default: github-runner
# Results in names like: github-runner-orchestrated-abc12345-xyz789
```

#### Monitoring Configuration

```bash
ORCHESTRATOR_POLL_INTERVAL=30
# Seconds between GitHub API polls
# Default: 30
# Recommendation: Don't go below 15 to avoid rate limits

ORCHESTRATOR_LOG_LEVEL=INFO
# Logging level: DEBUG, INFO, WARNING, ERROR
# Default: INFO

ORCHESTRATOR_STRUCTURED_LOGGING=true
# Enable JSON-formatted structured logging
# Default: true
```

#### Docker Configuration

```bash
ORCHESTRATOR_DOCKER_SOCKET=unix:///var/run/docker.sock
# Docker daemon socket
# Default: unix:///var/run/docker.sock
```

### Configuration Scenarios

#### Small Team (1-5 developers, light usage)

```bash
ORCHESTRATOR_MIN_RUNNERS=1
ORCHESTRATOR_MAX_RUNNERS=3
ORCHESTRATOR_SCALE_UP_THRESHOLD=2
ORCHESTRATOR_SCALE_DOWN_THRESHOLD=0
ORCHESTRATOR_POLL_INTERVAL=60
```

#### Medium Team (5-20 developers, moderate usage)

```bash
ORCHESTRATOR_MIN_RUNNERS=2
ORCHESTRATOR_MAX_RUNNERS=10
ORCHESTRATOR_SCALE_UP_THRESHOLD=3
ORCHESTRATOR_SCALE_DOWN_THRESHOLD=1
ORCHESTRATOR_POLL_INTERVAL=30
```

#### Large Team (20+ developers, heavy usage)

```bash
ORCHESTRATOR_MIN_RUNNERS=5
ORCHESTRATOR_MAX_RUNNERS=20
ORCHESTRATOR_SCALE_UP_THRESHOLD=5
ORCHESTRATOR_SCALE_DOWN_THRESHOLD=2
ORCHESTRATOR_POLL_INTERVAL=15
```

---

## 🔧 Orchestrator Components

### Background Tasks

The orchestrator runs **6 concurrent background tasks** (asyncio tasks):

#### 1. Queue Monitor (`_monitor_queue`)
**Runs every**: `POLL_INTERVAL` seconds (default: 30s)

**What it does**:
- Polls GitHub API for queued and in-progress workflow runs
- Calculates effective queue length
- Triggers scale-up if queue ≥ threshold
- Triggers scale-down if queue ≤ threshold
- Implements circuit breaker safety check

**Key logic**:
```python
queue_length = (queued_jobs + in_progress_jobs) - available_runners
if queue_length >= SCALE_UP_THRESHOLD:
    scale_up()
elif queue_length <= SCALE_DOWN_THRESHOLD:
    scale_down()
```

#### 2. Minimum Runner Maintainer (`_maintain_minimum_runners`) **NEW**
**Runs every**: 60 seconds

**What it does**:
- Counts ONLINE runners (not just registered or running containers)
- Creates new runners if below minimum
- Critical for automatic replacement of dead/offline runners
- Respects circuit breaker and container limits

**Key logic**:
```python
online_runners = count(runners where status == "online" AND running in Docker)
if online_runners < MIN_RUNNERS:
    create_runners(needed = MIN_RUNNERS - online_runners)
```

**Why this is important**: This task ensures your minimum capacity is always maintained. If a runner crashes or goes offline, it will be replaced within 60 seconds.

#### 3. Runner Manager (`_manage_runners`)
**Runs every**: 30 seconds

**What it does**:
- Tracks active runner containers
- Updates internal state with container health
- Removes dead containers from tracking
- Provides health metrics

#### 4. Sync Task (`_sync_runners`)
**Runs every**: 2 minutes

**What it does**:
- **Removes orphaned GitHub runners**: Runners registered in GitHub but no longer running in Docker
- **Removes unregistered containers**: Containers running for >2 minutes but not registered in GitHub
- Cleans up state inconsistencies between GitHub and Docker

**Why this matters**: Prevents ghost runners and failed registration attempts from cluttering your runner pool.

#### 5. Dead Container Cleanup (`_cleanup_dead_containers`)
**Runs every**: 5 minutes

**What it does**:
- Finds containers with status "exited" or "dead"
- Removes containers and associated volumes
- Updates metrics

#### 6. Utilization Monitor (`_monitor_runner_utilization`)
**Runs every**: 60 seconds

**What it does**:
- Calculates runner utilization percentage
- Triggers scale-up if utilization ≥ 80% and jobs queued
- Triggers scale-down if utilization ≤ 20% and above minimum

**Utilization calculation**:
```python
utilization = (busy_runners / total_runners) * 100
```

### Core Clients

#### GitHubClient (`src/github_client.py`)

**Responsibilities**:
- Communicates with GitHub REST API
- Handles authentication and token validation
- Implements retry logic (3 attempts with exponential backoff)
- Supports both repo and org-level runners

**Key methods**:
- `get_runners()` - List managed runners (filters out non-orchestrated)
- `get_registration_token()` - Get token for new runner registration
- `delete_runner(id)` - Remove runner from GitHub
- `get_queue_length()` - Calculate current queue demand
- `get_workflow_runs(status)` - Get queued/in-progress workflows

#### DockerClient (`src/docker_client.py`)

**Responsibilities**:
- Manages runner containers via Docker API
- Creates containers with proper configuration
- Handles volume management
- Ensures network isolation

**Key methods**:
- `create_runner(name, url, token)` - Create new runner container
- `remove_runner(id, force)` - Stop and remove container + volume
- `get_runners()` - List all managed containers
- `cleanup_dead_containers()` - Remove exited containers

**Container configuration**:
- Image: Configurable (default: `shghar:local`)
- Volumes: Work directory + Docker socket + Docker lib
- Network: Dedicated bridge network
- Privileged: Yes (for Docker-in-Docker)
- Restart policy: `unless-stopped`

---

## 📊 Scaling Logic

### Decision Tree

```
Every 30 seconds (Queue Monitor):
  │
  ├─→ Check container count
  │   ├─→ If >= MAX_RUNNERS → Activate circuit breaker → STOP
  │   └─→ If < MAX_RUNNERS → Deactivate circuit breaker → Continue
  │
  ├─→ Get queue length
  │   ├─→ queue >= SCALE_UP_THRESHOLD?
  │   │   └─→ YES → Scale up (create up to 2 runners)
  │   │
  │   └─→ queue <= SCALE_DOWN_THRESHOLD?
  │       └─→ YES → Scale down (remove 1 idle runner if > MIN)
  │
  └─→ Log metrics

Every 60 seconds (Minimum Maintainer):
  │
  ├─→ Count ONLINE runners (status=="online" in GitHub)
  │
  ├─→ online_count < MIN_RUNNERS?
  │   └─→ YES → Create (MIN - online_count) runners
  │   └─→ NO → Do nothing
  │
  └─→ Respect MAX_RUNNERS limit

Every 60 seconds (Utilization Monitor):
  │
  ├─→ Calculate utilization = (busy / total) * 100
  │
  ├─→ utilization >= 80% AND total < MAX?
  │   └─→ YES → Scale up
  │
  └─→ utilization <= 20% AND total > MIN?
      └─→ YES → Scale down
```

### Scaling Constraints

**Scale Up Constraints**:
1. Never exceed `MAX_RUNNERS` containers
2. Create maximum 2 runners per scaling action
3. 60-second cooldown between scale-up actions
4. Must have available registration tokens from GitHub

**Scale Down Constraints**:
1. Never go below `MIN_RUNNERS`
2. Remove maximum 1 runner per scaling action
3. Only remove idle (not busy) runners
4. Remove oldest runners first (FIFO)

### Example Scenarios

#### Scenario 1: Morning Rush

```
Time: 9:00 AM - Developers start pushing code
State: 2 runners (minimum), both idle

9:01 - 5 workflows queued
  → Queue monitor: queue_length = 5, threshold = 3
  → Scale up: Create 2 runners
  → New state: 4 runners (2 online, 2 registering)

9:02 - New runners register
  → State: 4 runners online, all busy

9:03 - 3 more workflows queued
  → Queue monitor: queue_length = 3
  → Scale up: Create 2 more runners
  → New state: 6 runners

9:05 - Jobs complete
  → Utilization drops to 30%
  → Keep all runners (utilization > 20%)

9:10 - All jobs done
  → Utilization: 0%
  → Utilization monitor: Scale down to minimum
  → Over next 5 minutes: Remove 4 runners
  → Final state: 2 runners (minimum)
```

#### Scenario 2: Runner Failure

```
Time: 2:00 PM - Stable state
State: 2 runners online

2:05 - Runner 1 crashes (Docker container exits)
  → Docker state: 1 container running
  → GitHub state: 2 runners (1 online, 1 offline)

2:06 - Minimum maintainer runs
  → Counts: 1 online runner
  → Needed: 2 - 1 = 1
  → Creates: 1 new runner
  → State: 2 containers (1 old, 1 new registering)

2:07 - New runner registers
  → State: 2 online runners
  → Minimum restored

2:08 - Sync task runs
  → Detects orphaned offline runner in GitHub
  → Removes from GitHub
  → Clean state achieved
```

---

## 📡 API Documentation

### Base URL
```
http://localhost:8080
```

### Endpoints

#### GET `/health`
Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "orchestrator_running": true
}
```

#### GET `/api/v1/status`
Detailed orchestrator status.

**Response**:
```json
{
  "orchestrator": {
    "running": true,
    "uptime": "N/A"
  },
  "runners": {
    "active": 2,
    "docker_containers": 2,
    "registered_running": 2,
    "unregistered_running": 0,
    "total_created": 15,
    "total_destroyed": 13,
    "ignored_existing": 0
  },
  "queue": {
    "current_length": 0,
    "last_poll": "2025-10-29T13:26:05.429964Z"
  },
  "scaling": {
    "min_runners": 2,
    "max_runners": 10,
    "scale_up_threshold": 3,
    "scale_down_threshold": 1,
    "last_action": {
      "action": "scale_up",
      "timestamp": "2025-10-29T12:00:00Z",
      "runners_added": 2
    }
  },
  "settings": {
    "poll_interval": 30,
    "idle_timeout": 300,
    "runner_image": "shghar:local"
  }
}
```

#### GET `/api/v1/runners`
List all runners (both Docker and GitHub).

**Response**:
```json
{
  "docker_runners": [
    {
      "id": "abc123",
      "name": "github-runner-orchestrated-abc12345",
      "status": "running",
      "runner_name": "orchestrated-abc12345",
      "created_at": "2025-10-29T12:00:00Z",
      "image": "shghar:local"
    }
  ],
  "github_runners": [
    {
      "id": 123456,
      "name": "orchestrated-abc12345",
      "status": "online",
      "busy": false,
      "labels": ["self-hosted", "orchestrated", "linux"]
    }
  ]
}
```

#### POST `/api/v1/runners/scale-up`
Manually trigger scale up.

**Response**:
```json
{
  "message": "Scale up triggered",
  "runners_created": 2
}
```

#### POST `/api/v1/runners/scale-down`
Manually trigger scale down.

**Response**:
```json
{
  "message": "Scale down triggered",
  "runners_removed": 1
}
```

#### GET `/api/v1/runners/{runner_id}/logs`
Get logs from a specific runner container.

**Parameters**:
- `runner_id`: Docker container ID
- `tail`: Number of lines (default: 100)

**Response**:
```json
{
  "container_id": "abc123",
  "logs": "2025-10-29 12:00:00Z: Listening for Jobs\n..."
}
```

#### DELETE `/api/v1/runners/{runner_id}`
Remove a specific runner.

**Response**:
```json
{
  "message": "Runner removed successfully",
  "runner_id": "abc123"
}
```

#### GET `/api/v1/metrics`
Prometheus-compatible metrics.

**Response** (text/plain):
```
# HELP runners_total Total number of runners
# TYPE runners_total gauge
runners_total{status="active"} 2

# HELP runners_created_total Total runners created
# TYPE runners_created_total counter
runners_created_total 15

# HELP queue_length Current GitHub Actions queue length
# TYPE queue_length gauge
queue_length 0
```

#### GET `/docs`
Interactive API documentation (Swagger UI).

---

## 📈 Monitoring & Observability

### Logging

**Structured JSON Logs** (when `STRUCTURED_LOGGING=true`):
```json
{
  "event": "Scaling to minimum runners",
  "current_online": 1,
  "needed": 1,
  "safe_needed": 1,
  "docker_running": 1,
  "docker_total": 1,
  "logger": "src.orchestrator",
  "level": "info",
  "timestamp": "2025-10-29T13:26:05.429964Z"
}
```

**Log Levels**:
- `DEBUG`: Detailed operational information
- `INFO`: Normal operational events (default)
- `WARNING`: Unexpected but handled situations
- `ERROR`: Error conditions requiring attention

**Viewing Logs**:
```bash
# Follow orchestrator logs
docker-compose logs -f orchestrator

# Filter by level
docker-compose logs orchestrator | grep '"level":"error"'

# Filter by event
docker-compose logs orchestrator | grep "Scaling to minimum"

# View runner logs
docker logs github-runner-orchestrated-abc12345
```

### Metrics

**Tracked Metrics**:
- `total_runners_created`: Lifetime count of created runners
- `total_runners_destroyed`: Lifetime count of destroyed runners
- `current_queue_length`: Current GitHub Actions queue length
- `last_scale_action`: Most recent scaling action and timestamp
- `failed_scale_attempts`: Consecutive failures (circuit breaker trigger)
- `circuit_breaker_active`: Emergency brake status

**Accessing Metrics**:
```bash
# Via API
curl http://localhost:8080/api/v1/status | jq

# Via Prometheus (if configured)
curl http://localhost:8080/api/v1/metrics
```

### Prometheus Integration

**prometheus.yml** (included):
```yaml
scrape_configs:
  - job_name: 'orchestrator'
    static_configs:
      - targets: ['orchestrator:8080']
    metrics_path: '/api/v1/metrics'
    scrape_interval: 30s
```

**Start Prometheus**:
```bash
docker-compose up -d prometheus
# Access: http://localhost:9090
```

**Useful Queries**:
```promql
# Current active runners
runners_total{status="active"}

# Runner creation rate (per hour)
rate(runners_created_total[1h]) * 3600

# Queue length over time
queue_length

# Circuit breaker status
circuit_breaker_active
```

### Diagnostic Script

**diagnose-runners.sh** - Comprehensive diagnostic tool:

```bash
./diagnose-runners.sh
```

**Output includes**:
1. Current runner containers
2. Recent container logs
3. Container inspection (state, config, mounts)
4. Available Docker images
5. Network status
6. Orchestrator logs (last 20 lines)

---

## 🔍 Troubleshooting

### Common Issues

#### 1. Orchestrator Won't Start

**Symptoms**:
- Container exits immediately
- Error in logs: "GitHub token validation failed"

**Solution**:
```bash
# Check logs
docker-compose logs orchestrator

# Verify token
curl -H "Authorization: token YOUR_TOKEN" \
  https://api.github.com/user

# Verify token has correct scopes
curl -H "Authorization: token YOUR_TOKEN" \
  https://api.github.com/repos/OWNER/REPO/actions/runners
```

**Required Permissions**:
- Fine-grained PAT: `Actions: Read and write`, `Administration: Read and write`
- Classic PAT: `repo` scope (for repos) or `admin:org` (for orgs)

#### 2. Runners Not Registering

**Symptoms**:
- Containers start but never show as "online" in GitHub
- Logs show connection errors

**Debug Steps**:
```bash
# Check runner logs
docker logs github-runner-orchestrated-XXXXX

# Check network connectivity
docker exec github-runner-orchestrated-XXXXX ping github.com

# Verify registration token
docker exec github-runner-orchestrated-XXXXX env | grep RUNNER_TOKEN

# Check if container can reach GitHub API
docker exec github-runner-orchestrated-XXXXX \
  curl -I https://api.github.com
```

**Common causes**:
- Network firewall blocking GitHub
- Expired registration token
- Incorrect `REPO_URL`

#### 3. Minimum Runners Not Maintained

**Symptoms**:
- Fewer than `MIN_RUNNERS` online
- Dead runners not replaced

**Debug Steps**:
```bash
# Check background task status
docker-compose logs orchestrator | grep "maintain_minimum_runners"

# Check runner count analysis
docker-compose logs orchestrator | grep "Runner count analysis"

# Verify minimum maintainer is running
docker-compose logs orchestrator | grep "Scaling to minimum"
```

#### 4. Scaling Not Working

**Symptoms**:
- Queue builds up but no new runners created
- Idle runners not removed

**Debug Steps**:
```bash
# Check current status
curl http://localhost:8080/api/v1/status | jq

# Check scaling debug logs
docker-compose logs orchestrator | grep "SCALING DEBUG"

# Verify queue monitoring
docker-compose logs orchestrator | grep "Queue monitoring"

# Check if circuit breaker is active
docker-compose logs orchestrator | grep "circuit_breaker.*true"
```

**Common causes**:
- Circuit breaker activated (check logs)
- Already at MAX_RUNNERS
- Cooldown period active (60s between scale-ups)
- GitHub API rate limit exceeded

#### 5. Too Many Containers Created

**Symptoms**:
- Container count exceeds MAX_RUNNERS
- Runaway scaling

**Emergency Stop**:
```bash
# Stop orchestrator immediately
docker-compose stop orchestrator

# Remove all runner containers
docker ps --filter label=managed-by=runner-orchestrator -q | xargs docker rm -f

# Check what happened
docker-compose logs orchestrator | grep -E "(EMERGENCY|circuit_breaker)"
```

**Prevention**:
- Circuit breaker should prevent this (checks container count before every action)
- If this happens, file a bug report!

#### 6. Orphaned Runners in GitHub

**Symptoms**:
- Runners in GitHub UI but not in Docker
- Many "offline" runners

**Solution**:
```bash
# Wait for sync task (runs every 2 minutes)
# Or manually trigger cleanup via API

# Check sync task logs
docker-compose logs orchestrator | grep "Found orphaned runners"

# Sync task should clean these up automatically
# If not, check:
docker-compose logs orchestrator | grep "_sync_runners"
```

### Debug Mode

Enable detailed logging:

```bash
# In .env
ORCHESTRATOR_LOG_LEVEL=DEBUG

# Restart
docker-compose restart orchestrator

# View detailed logs
docker-compose logs -f orchestrator
```

### Health Checks

```bash
# Orchestrator health
curl http://localhost:8080/health

# Detailed status
curl http://localhost:8080/api/v1/status | jq

# Runner list
curl http://localhost:8080/api/v1/runners | jq

# Check GitHub directly
curl -H "Authorization: token YOUR_TOKEN" \
  https://api.github.com/repos/OWNER/REPO/actions/runners | jq
```

---

## 🚀 Advanced Usage

### Custom Runner Image

The orchestrator uses a **custom-built runner image** defined in `runner-image/Dockerfile` and `runner-image/entrypoint.sh`. This provides full control over the runner environment and dependencies.

**Default image structure** (`runner-image/Dockerfile`):

```dockerfile
FROM ubuntu:22.04

# Install GitHub Actions runner dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    jq \
    build-essential \
    libssl-dev \
    # ... other dependencies

# Download and install GitHub Actions runner
# Configure Docker-in-Docker support
# Set up entrypoint script

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
```

**Customizing the runner image**:

Edit `runner-image/Dockerfile` to add your tools:

```dockerfile
# Add after existing RUN commands

# Install additional tools
RUN apt-get install -y \
    python3-pip \
    nodejs \
    npm \
    postgresql-client \
    awscli

# Install language-specific dependencies
RUN pip3 install boto3 requests pytest

# Add custom scripts
COPY custom-scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/*
```

**Build and deploy**:
```bash
# Build the custom runner image
docker build -t shghar:local -f runner-image/Dockerfile runner-image/

# Update .env to use your custom image
ORCHESTRATOR_RUNNER_IMAGE=shghar:local

# Restart orchestrator to use new image
docker-compose restart orchestrator
```

**The entrypoint script** (`runner-image/entrypoint.sh`) handles:
- Runner registration with GitHub
- Docker-in-Docker configuration
- Graceful shutdown and de-registration
- Environment variable management
- Signal handling for clean container stops

### Custom Runner Labels

**Use labels for job targeting**:

```bash
# In .env
ORCHESTRATOR_RUNNER_LABELS=self-hosted,orchestrated,gpu,cuda-11

# In workflow
jobs:
  gpu-job:
    runs-on: [self-hosted, gpu]
```

### Multiple Orchestrators

**Run separate orchestrators for different projects**:

```bash
# Project A
cd project-a-runners
ORCHESTRATOR_GITHUB_REPO=org/project-a \
ORCHESTRATOR_MIN_RUNNERS=2 \
docker-compose up -d

# Project B
cd project-b-runners
ORCHESTRATOR_GITHUB_REPO=org/project-b \
ORCHESTRATOR_MIN_RUNNERS=5 \
docker-compose up -d
```

### Organization-Level Runners

**For entire organization**:

```bash
# In .env
ORCHESTRATOR_GITHUB_ORG=my-company
# Remove or comment out ORCHESTRATOR_GITHUB_REPO

# Requires PAT with admin:org scope
```

**Note**: Queue-based scaling doesn't work for org-level runners (GitHub API limitation). Utilization-based scaling and minimum maintenance still work.

### Resource Limits

**Limit runner container resources**:

Edit `docker_client.py`:

```python
container_config = {
    # ...existing config...
    "mem_limit": "4g",      # 4GB RAM limit
    "memswap_limit": "4g",  # No swap
    "cpu_quota": 200000,    # 2 CPU cores
    "cpu_period": 100000,
}
```

### Persistent Runner Storage

**Use bind mounts for runner workspace**:

Edit `docker_client.py`:

```python
"volumes": {
    "/data/runner-workspace": {"bind": "/actions-runner/_work", "mode": "rw"},
    # ...other volumes...
}
```

---

## 🔄 Migration from v1.0

### What Changed

**v1.0 (Static Runner)**:
- Single container runs continuously
- Manual scaling required
- No automatic recovery
- Limited observability

**v2.0 (Orchestrator)**:
- Multiple ephemeral containers
- Automatic scaling
- Self-healing (dead runner replacement)
- Full REST API and metrics

### Migration Steps

```bash
# 1. Backup existing setup
docker-compose down
cp docker-compose.yml docker-compose.yml.backup
cp .env .env.backup

# 2. Update repository
git pull origin main

# 3. Update .env with new format
# See Configuration section

# 4. Remove old containers
docker ps -a | grep runner | awk '{print $1}' | xargs docker rm -f

# 5. Build new runner image
docker build -t shghar:local -f runner-image/Dockerfile .

# 6. Start orchestrator
docker-compose up -d

# 7. Verify
./diagnose-runners.sh
```

### Workflow Compatibility

**No changes needed!** Existing workflows work automatically:

```yaml
# This still works
jobs:
  build:
    runs-on: self-hosted
```

**Recommended**: Use specific labels for better control:

```yaml
jobs:
  build:
    runs-on: [self-hosted, orchestrated]
```

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (outside Docker)
export ORCHESTRATOR_GITHUB_TOKEN=xxx
export ORCHESTRATOR_GITHUB_REPO=owner/repo
python main.py

# Run tests
pytest tests/

# Lint
black src/
pylint src/
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Based on [myoung34/docker-github-actions-runner](https://github.com/myoung34/docker-github-actions-runner)
- Inspired by Kubernetes autoscaling patterns
- Built with FastAPI, Docker SDK, and GitHub API

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/self-hosted-github-action-runner/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/self-hosted-github-action-runner/discussions)
- **Documentation**: This README and `/docs` API endpoint

---

**Last Updated**: November 2, 2025
**Version**: 2.0.0
