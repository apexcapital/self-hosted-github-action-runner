# Self-Hosted Github Action Runner - Containerized (Docker)
## self-hosted-github-action-runner

_A Dockerized self-hosted GitHub Actions runenr, designed for easy open-source reuse.
Designed for turn-key deployment to any Docker host environment._

### [Docker Compose](#compose-quickstart) and [Docker CLI](#cli-quickstart) are both supported

The only configuration is to copy the provided `.env.example` to `.env` and populate it accordingly.

## Features
  - **Auto-registraion of runner from any Docker host with access to `github.com`**
  - **Self-cleanup of runner on container termination**
  - **Provided images for `linux/amd64` and `linux/arm64`**

---

## Table of Contents

  - [CLI-Quickstart](#cli-quickstart)
  - [Compose-Quickstart](#compose-quickstart)
  - [Environment Variables](#environment-variables)
  - [Updating Runner Version](#updating-runner-version)
  - [Cleanup](#cleanup)
  - [Contributing](#contributing)
  - [License](#license)


## CLI-Quickstart

1. (Optional) Create a work directory to persist the workspace.
    ```bash
    mkdir -p ~/runner-work
    ```

2. Run the container (replacing `<OWNER>`, `<REPO>`, `YOUR_TOKEN`)
    ```bash
    docker run -d \
    --name my-self-hosted-runner \
    --restart unless-stopped \
    -e REPO_URL="https://github.com/<OWNER>/<REPO>" \
    -e RUNNER_TOKEN="<YOUR_TOKEN>" \
    -e RUNNER_NAME="my-self-hosted-runner" \
    -e RUNNER_WORKDIR="_work" \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v ~/runner-work:/actions-runner/_work \
    ghcr.io/velvet-labs-llc/runner:latest
    ```

3. (Alternative) Use an `.env` file
  
    Create a file called `runner.env` with:
    ```bash
    REPO_URL=https://github.com/<OWNER>/<REPO>
    RUNNER_TOKEN=<YOUR_TOKEN>
    RUNNER_NAME=my-self-hosted-runner
    RUNNER_WORKDIR=_work
    ```

    Then:
    ```bash
    docker run -d \
    --name my-self-hosted-runner \
    --restart unless-stopped \
    --env-file runner.env \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v ~/runner-work:/actions-runner/_work \
    ghcr.io/velvet-labs-llc/runner:latest
    ```

4. View logs and verify
    ```bash
    docker logs -f my-self-hosted-runner
    ```

## Compose-Quickstart

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

The runner will handle updating itself anytime it polls GitHub and sees a new version available.

You may manually specify a version via the `RUNNER_VERSION` environment variable.

## Cleanup

*Docker CLI:* Remove the running container and image if no longer needed:
```bash
docker rm -f my-self-hosted-runner
docker rmi ghcr.io/velvet-labs-llc/runner:latest
```

*Compose:* Remove containers, networks, and volumes:

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

