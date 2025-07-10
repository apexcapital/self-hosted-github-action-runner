# Self-Hosted Github Action Runner - Containerized (Docker)
## self-hosted-github-action-runner

_A Dockerized self-hosted GitHub Actions runenr, designed for easy open-source reuse.
Designed for turn-key deployment to any Docker host environment._

The only configuration is to copy the provided `.env.example` to `.env` and populate it accordingly.

## Features
  - **Auto-registraion of runner from any Docker host with access to `github.com`**
  - **Self-cleanup of runner on container termination**

## Quickstart

1. Clone repo  
   ```bash
   git clone https://github.com/your-org/self-hosted-github-action-runner.git # or
   git clone git@github.com:Velvet-Labs-LLC/self-hosted-github-action-runner.git

   cd self-hosted-github-action-runner
    ```

2. Copy config

   ```bash
   cp .env.example .env
   # fill in variables: RUNNER_VERSION, REPO_URL, RUNNER_TOKEN, RUNNER_NAME, etc.
   ```

3. Build & Run

   ```bash
   docker compose up -d --build
   ```

4. Verify

   * Check that the runner appears under **Settings → Actions → Runners** for your repo/org.

## Environment Variables

_NOTE_: You can get the latest version of the Github Runner package by running the following `curl`:
  ```bash
  curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//'
  ```

Define these in your `.env` (see `.env.example`):

* **RUNNER\_VERSION**
  GitHub Actions runner version (default in Dockerfile: `2.325.0`).

* **REPO\_URL**
  URL of your GitHub repo or organization, e.g. `https://github.com/owner/repo`.

* **RUNNER\_TOKEN**
  Self-hosted runner token (generate under **Settings → Actions → Runners**).

* **RUNNER\_NAME**
  Friendly name for this runner instance (defaults to the container’s hostname).

* **RUNNER\_WORKDIR** *(optional)*
  Workspace directory inside the container (default: `_work`).

## Updating Runner Version

To bump the runner to a newer release:

```bash
# Option A: via Docker Compose
# (Compose reads RUNNER_VERSION from .env and passes it to build args)
docker compose build
docker compose up -d

# Option B: direct docker build
docker build \
  --build-arg RUNNER_VERSION=2.325.0 \
  -t my-runner:2.325.0 .
docker run -d my-runner:2.325.0
```

## Cleanup

Remove containers, networks, and volumes:

```bash
docker compose down --volumes
```

## Contributing

Contributions are welcome! Please:

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/foo`)
3. Commit your changes (`git commit -m "Add foo feature"`)
4. Push to the branch (`git push origin feature/foo`)
5. Open a Pull Request

## License

Distributed under the MIT License.

