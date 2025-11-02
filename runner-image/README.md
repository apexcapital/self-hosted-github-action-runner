# Custom GitHub Actions Self-Hosted Runner Image

A production-ready, optimized Docker image for self-hosted GitHub Actions runners with Docker-in-Docker (DinD) support
and full Playwright browser testing capabilities.

## Overview

This custom runner image is designed to be managed by an orchestrator application that dynamically provisions and scales
runners using Docker commands. The image is built on Debian Bookworm Slim and includes:

- **GitHub Actions Runner** (v2.328.0)
- **Docker-in-Docker (DinD)** support for containerized workflows
- **Playwright** browser testing dependencies (all mandatory system libraries)
- **Node.js** (configurable version, default: 22 LTS) via NodeSource
- **Python 3** with pip and venv
- **Non-root execution** via the `actions` user for security
- **Hardened security** with setuid/setgid removal and strict permissions
- **Configurable runtime environment** via orchestrator settings

## Image Architecture

### Multi-Stage Build

The Dockerfile uses a multi-stage build pattern to optimize the final image size:

1. **Builder Stage**: Downloads and extracts the GitHub Actions runner binaries for the target architecture (x64/arm64)
   with integrity verification
2. **Runtime Stage**: Assembles the complete runtime environment with all dependencies

### Target Architectures

- `amd64` / `x86_64` (default)
- `arm64` / `aarch64`

Architecture detection is automatic via the `TARGETARCH` build argument.

## Installed Components

### Core Utilities

```
ca-certificates, curl, gnupg, wget, gosu, jq, xz-utils, pigz
iptables, iproute2, unzip, zip, git
```

### Docker Engine Stack

- `docker-ce` - Docker Engine
- `docker-ce-cli` - Docker CLI
- `containerd.io` - Container runtime
- `docker-buildx-plugin` - BuildKit builder
- `docker-compose-plugin` - Compose V2

### Python Environment

- `python3` - Python 3.x from Debian repos
- `python3-venv` - Virtual environment support
- `python3-pip` - Package installer

### Node.js

- **Node.js** installed via NodeSource repository (version configurable at build time)
- Default: Node.js 22 LTS
- Ensures latest LTS features and security updates
- Optimized npm configuration (fund/audit messages disabled for cleaner output)
- Version can be customized via `NODE_VERSION` build argument

## Playwright Dependencies

The image includes **all mandatory system dependencies** for Playwright browser automation. These libraries are required
for Chromium, Firefox, and WebKit browsers to function properly in headless and headed modes.

### Core Graphics & X11

```
libglib2.0-0, libnspr4, libnss3, libdbus-1-3
libatk1.0-0, libatk-bridge2.0-0, libcups2
libxcb1, libxkbcommon0, libatspi2.0-0
libx11-6, libxcomposite1, libxdamage1, libxext6, libxfixes3, libxrandr2
libgbm1, libdrm2, libxshmfence1, libxcursor1, libx11-xcb1
```

### GTK & Rendering

```
libgtk-3-0, libgdk-pixbuf-2.0-0, libpangocairo-1.0-0, libcairo-gobject2  # GTK 3
libgtk-4-1, libgraphene-1.0-0                                            # GTK 4
```

### GStreamer (Media Playback)

```
libgstreamer1.0-0
libgstreamer-plugins-base1.0-0
libgstreamer-plugins-bad1.0-0
libgstreamer-gl1.0-0
```

### Media Codecs & Libraries

```
libxslt1.1, libwoff1, libvpx7, libevent-2.1-7, libopus0, libflite1
libwebpdemux2, libavif15, libharfbuzz-icu0, libwebpmux3
libenchant-2-2, libsecret-1-0, libhyphen0, libmanette-0.2-0
libgles2, libx264-164
```

### Fonts & Utilities

```
xdg-utils                      # Desktop integration
fonts-liberation               # Liberation fonts (metrics-compatible with Arial, Times, Courier)
fonts-noto-core                # Noto Sans/Serif
fonts-noto-color-emoji         # Color emoji support
ffmpeg                         # Video/audio processing
libu2f-udev                    # U2F authentication device support
```

> **Note**: All these dependencies have been verified as mandatory for Playwright. Removing any package may cause
> browser launch failures or rendering issues.

## User & Permissions

- **User**: `actions` (non-root)
- **Group**: `actions`
- **Home**: `/home/actions`
- **Workdir**: `/actions-runner`

The runner executes as the `actions` user for security. The entrypoint uses `gosu` to drop privileges from root to
`actions` when starting the runner and dockerd.

### Docker Socket Access

When using a host Docker socket (bind-mounted `/var/run/docker.sock`), the entrypoint automatically:

1. Detects the socket's group ID
2. Creates or reuses a matching group
3. Adds the `actions` user to that group

This ensures the non-root runner can communicate with the Docker daemon regardless of host GID variations.

## Environment Variables

### Required (Orchestrator-Provided)

- `REPO_URL` - GitHub repository or organization URL (e.g., `https://github.com/user/repo`)
- `RUNNER_TOKEN` - Registration token from GitHub API
- `RUNNER_NAME` - Unique name for this runner instance (defaults to hostname)

### Optional Configuration

| Variable                           | Default                                   | Description                                                                            |
|------------------------------------|-------------------------------------------|----------------------------------------------------------------------------------------|
| `RUNNER_LABELS`                    | `""`                                      | Comma-separated custom labels for this runner                                          |
| `NO_DEFAULT_LABELS`                | `false`                                   | If `true`, skip appending default labels                                               |
| `DEFAULT_LABELS`                   | `docker-dind,linux,self-hosted,optimized` | Auto-appended labels (unless disabled)                                                 |
| `RUNNER_WORKDIR`                   | `_work`                                   | Workspace directory for job execution                                                  |
| `START_DOCKER_SERVICE`             | `true`                                    | If `false`, skip starting dockerd (use host socket)                                    |
| `DISABLE_AUTOMATIC_DEREGISTRATION` | `false`                                   | If `true`, skip runner unregistration on shutdown                                      |
| `UNSET_CONFIG_VARS`                | `false`                                   | If `true` with deregistration disabled, unset `RUNNER_TOKEN` & `REPO_URL` after config |
| `DEBUG_OUTPUT`                     | `false`                                   | Enable `set -x` for entrypoint debugging                                               |

### Docker Daemon Configuration

| Variable               | Default           | Description                                         |
|------------------------|-------------------|-----------------------------------------------------|
| `DOCKER_DATA_ROOT`     | `/var/lib/docker` | Docker storage directory                            |
| `DOCKER_DRIVER`        | `overlay2`        | Storage driver                                      |
| `DOCKER_CGROUP_DRIVER` | `cgroupfs`        | Cgroup driver (use `systemd` for K8s)               |
| `DOCKERD_LOG_LEVEL`    | `info`            | Daemon log level (`debug`, `info`, `warn`, `error`) |
| `DOCKER_BUILDKIT`      | `1`               | Enable BuildKit                                     |

### Playwright Configuration

| Variable                   | Default          | Description                                                          |
|----------------------------|------------------|----------------------------------------------------------------------|
| `PLAYWRIGHT_BROWSERS_PATH` | `/ms-playwright` | Browser cache directory (configurable via orchestrator)              |
| `CI`                       | `true`           | Signals CI environment to Playwright (configurable via orchestrator) |

### Node.js Configuration

| Variable   | Default      | Description                                              |
|------------|--------------|----------------------------------------------------------|
| `NODE_ENV` | `production` | Node.js environment mode (configurable via orchestrator) |

> **Note**: The orchestrator application automatically configures `CI`, `PLAYWRIGHT_BROWSERS_PATH`, and `NODE_ENV`
> based on its settings (`.env` file). The defaults shown above are fallback values if not overridden at runtime.

## Volumes

- `/var/lib/docker` - Docker daemon state (optional; can use host socket instead)
- `/actions-runner/_work` - Job workspace (ephemeral)
- `/actions-runner/_tool` - Tool cache

## Entrypoint Flow

The `entrypoint.sh` script orchestrates the runner lifecycle:

1. **Label Construction**: Combines custom and default labels
2. **Docker-in-Docker**: Starts `dockerd` if `START_DOCKER_SERVICE=true`
3. **Socket Access**: Configures Docker socket permissions for `actions` user
4. **Runner Registration**: Calls `config.sh` with GitHub credentials (if not already registered)
5. **Runner Execution**: Launches `run.sh` as `actions` user
6. **Cleanup**: Traps signals to gracefully unregister runner and stop dockerd

### Signal Handling

- `SIGINT` / `SIGTERM` → Graceful shutdown (stop runner, unregister, stop dockerd)
- `EXIT` → Cleanup hook (unregister if enabled, stop dockerd)

## Usage Examples

### With Orchestrator (Recommended)

The orchestrator application automatically configures all runtime environment variables:

```bash
docker run -d \
  --privileged \
  --name runner-abc123 \
  -e REPO_URL="https://github.com/myorg/myrepo" \
  -e RUNNER_TOKEN="$(get_token_from_github_api)" \
  -e RUNNER_NAME="runner-abc123" \
  -e RUNNER_LABELS="playwright,premium" \
  -e NODE_ENV="production" \
  -e CI="true" \
  -e PLAYWRIGHT_BROWSERS_PATH="/ms-playwright" \
  custom-runner-image:latest
```

> The orchestrator sets `NODE_ENV`, `CI`, and `PLAYWRIGHT_BROWSERS_PATH` automatically based on its configuration.

### With Host Docker Socket (No DinD)

```bash
docker run -d \
  --name runner-xyz789 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e REPO_URL="https://github.com/myorg/myrepo" \
  -e RUNNER_TOKEN="$TOKEN" \
  -e RUNNER_NAME="runner-xyz789" \
  -e START_DOCKER_SERVICE=false \
  custom-runner-image:latest
```

### Custom Environment Configuration

Override default environment settings for specific use cases:

```bash
docker run -d \
  --privileged \
  -e REPO_URL="https://github.com/myorg/myrepo" \
  -e RUNNER_TOKEN="$TOKEN" \
  -e NODE_ENV="development" \
  -e PLAYWRIGHT_BROWSERS_PATH="/custom/playwright" \
  custom-runner-image:latest
```

### Ephemeral Runner (No Deregistration)

For runners that auto-scale and should remain registered:

```bash
docker run -d \
  --privileged \
  -e REPO_URL="https://github.com/myorg/myrepo" \
  -e RUNNER_TOKEN="$TOKEN" \
  -e DISABLE_AUTOMATIC_DEREGISTRATION=true \
  -e UNSET_CONFIG_VARS=true \
  custom-runner-image:latest
```

## Building the Image

From the repository root:

```bash
docker build \
  --platform linux/amd64 \
  -t custom-runner:latest \
  -f runner-image/Dockerfile \
  .
```

### Build Arguments

| Argument         | Default                | Description                                             |
|------------------|------------------------|---------------------------------------------------------|
| `RUNNER_VERSION` | `2.328.0`              | GitHub Actions runner version                           |
| `BASE_IMAGE`     | `debian:bookworm-slim` | Base Debian image                                       |
| `NODE_VERSION`   | `22`                   | Node.js major version to install (e.g., 18, 20, 22, 23) |
| `TARGETARCH`     | (auto-detected)        | Target architecture (`amd64`, `arm64`)                  |

### Custom Node.js Version

To build with a different Node.js version:

```bash
docker build \
  --build-arg NODE_VERSION=20 \
  -t custom-runner:node20 \
  -f runner-image/Dockerfile \
  .
```

### Multi-Architecture Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --build-arg NODE_VERSION=22 \
  -t custom-runner:latest \
  -f runner-image/Dockerfile \
  --push \
  .
```

## Size Optimization

The image is optimized for size while maintaining all required functionality:

- **Multi-stage build**: Separates build tools from runtime
- **`--no-install-recommends`**: Avoids unnecessary apt packages
- **Cleanup**: `rm -rf /var/lib/apt/lists/*` after each apt layer
- **Minimal base**: `debian:bookworm-slim` instead of full Debian
- **Download verification**: Validates runner tarball integrity during build
- **Optimized npm**: Disables fund/audit to reduce noise and overhead

## Security Considerations

1. **Non-Root Execution**: Runner processes run as `actions` user (UID/GID created at build time)
2. **Privileged Mode**: Required for DinD; orchestrator should apply security policies
3. **Token Management**: `RUNNER_TOKEN` can be unset after registration with `UNSET_CONFIG_VARS=true`
4. **Automatic Cleanup**: Runners auto-deregister on shutdown (unless disabled)
5. **Setuid/Setgid Hardening**: Unnecessary setuid/setgid bits removed from system binaries
6. **Explicit Permissions**: All files and directories have strict, validated permissions (755/644)
7. **File Validation**: Build fails if critical files are missing or have incorrect permissions
8. **OCI Labels**: Proper metadata for container registry compliance and traceability

### Security Hardening Details

The image implements several hardening measures:

- **Permission Hardening**: Removes setuid/setgid bits from `/usr/bin`, `/usr/sbin`, `/bin`, `/sbin` to prevent
  privilege escalation
- **Validated Copies**: All copied files (daemon.json, entrypoint.sh) are tested for existence and correct permissions
- **Strict File Modes**:
    - Executable scripts: `755`
    - Configuration files: `644`
    - Directories: `755`
- **Download Integrity**: Runner download is verified before extraction using `tar -tzf`

## Metadata & Labels

The image includes OCI-compliant labels for better container registry integration:

- `org.opencontainers.image.title`: GitHub Actions Self-Hosted Runner
- `org.opencontainers.image.description`: Custom runner with Docker-in-Docker and Playwright support
- `org.opencontainers.image.version`: Runner version (e.g., 2.328.0)
- `org.opencontainers.image.vendor`: Custom
- `maintainer`: nate.brandeburg

These labels enable better discovery and management in container registries and orchestration platforms.

## Troubleshooting

### Runner Fails to Register

- Verify `REPO_URL` and `RUNNER_TOKEN` are correct
- Check GitHub API rate limits
- Ensure network connectivity to `github.com`

### Playwright Browser Launch Fails

- Verify all dependencies are installed: `npx playwright install --with-deps --dry-run`
- Check `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` is set
- Ensure `/ms-playwright` is writable by `actions` user

### Docker-in-Docker Issues

- Confirm container runs with `--privileged` flag
- Check `dockerd` logs: `/var/log/dockerd.log` inside container
- Verify cgroup driver matches host (K8s typically needs `systemd`)

### Permission Errors with Host Socket

- Ensure `/var/run/docker.sock` is mounted with correct permissions
- Entrypoint autoconfigures group access; check logs for "Added user 'actions' to group"

### Build Failures

- **"daemon.json not found"**: Ensure `daemon.json` exists in repository root
- **"entrypoint.sh not executable"**: Check file permissions before build
- **"Runner download verification failed"**: Network issue or invalid runner version specified
- **"setuid removal failed"**: Non-critical; warning can be safely ignored

## Maintenance

### Updating Runner Version

Edit the `RUNNER_VERSION` build argument in `runner-image/Dockerfile`:

```dockerfile
ARG RUNNER_VERSION=2.329.0  # Update version
```

Or pass it at build time:

```bash
docker build --build-arg RUNNER_VERSION=2.329.0 -t custom-runner:latest -f runner-image/Dockerfile .
```

Rebuild the image.

### Updating Node.js Version

**Option 1: Build-time (Recommended)**

Use the `NODE_VERSION` build argument:

```bash
docker build --build-arg NODE_VERSION=23 -t custom-runner:node23 -f runner-image/Dockerfile .
```

**Option 2: Edit Dockerfile**

Change the default `NODE_VERSION` argument:

```dockerfile
ARG NODE_VERSION=23  # Update default version
```

**Option 3: Configure via Orchestrator**

Update the `.env` file in the orchestrator:

```bash
ORCHESTRATOR_NODE_VERSION=23
```

Then rebuild the image. The orchestrator will use this version when building runners.

### Changing Node.js Environment Mode

Edit the orchestrator's `.env` file:

```bash
# For development
ORCHESTRATOR_NODE_ENV=development

# For production (default)
ORCHESTRATOR_NODE_ENV=production
```

The orchestrator will automatically inject this into all runner containers.

### Customizing Playwright Configuration

Edit the orchestrator's `.env` file:

```bash
# Custom browser cache location
ORCHESTRATOR_PLAYWRIGHT_BROWSERS_PATH=/custom/playwright

# Disable CI mode (not recommended)
ORCHESTRATOR_CI=false
```

