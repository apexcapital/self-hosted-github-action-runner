"""Configuration management for the orchestrator."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # GitHub Configuration
    github_token: str = Field(..., description="GitHub Personal Access Token")
    github_org: Optional[str] = Field(
        None, description="GitHub organization (optional)"
    )
    github_repo: Optional[str] = Field(None, description="GitHub repository (optional)")

    # Runner Configuration
    runner_image: str = Field(
        "ghcr.io/apexcapital/runner:latest", description="Docker image for runners"
    )
    runner_version: str = Field("2.325.0", description="GitHub Actions runner version")

    runner_labels: str = Field(
        default="orchestrated,optimized,self-hosted,linux,x64,docker-dind",
        description="Comma-separated labels to assign to runners",
    )

    runner_disable_automatic_deregistration: bool = Field(
        False, description="Disable automatic deregistration on shutdown"
    )
    runner_unset_config_vars: bool = Field(
        True,
        description="Unset config vars before starting runner (prevents leaking to workflows)",
    )
    runner_start_docker_service: bool = Field(
        True, description="Auto-start Docker service in runner container"
    )
    runner_no_default_labels: bool = Field(
        False, description="Disable adding default self-hosted labels"
    )
    runner_debug_output: bool = Field(
        False, description="Enable additional debug output in runner"
    )

    # Scaling Configuration
    min_runners: int = Field(2, description="Minimum number of runners to maintain")
    max_runners: int = Field(10, description="Maximum number of runners")
    scale_up_threshold: int = Field(3, description="Queue length to trigger scale up")
    scale_down_threshold: int = Field(
        1, description="Queue length to trigger scale down"
    )
    idle_timeout: int = Field(
        300, description="Seconds before idle runners are terminated"
    )

    # Monitoring Configuration
    poll_interval: int = Field(30, description="Seconds between GitHub API polls")
    metrics_port: int = Field(9090, description="Port for Prometheus metrics")

    # Docker Configuration
    docker_socket: str = Field(
        "unix:///var/run/docker.sock", description="Docker daemon socket"
    )
    runner_network: str = Field(
        "runner-network", description="Docker network for runners"
    )

    # Logging Configuration
    log_level: str = Field("INFO", description="Logging level")
    structured_logging: bool = Field(True, description="Enable structured logging")

    # Redis Configuration (optional for distributed setups)
    redis_url: Optional[str] = Field(
        None, description="Redis URL for distributed coordination"
    )

    class Config:
        env_file = ".env"
        env_prefix = "ORCHESTRATOR_"


# Global settings instance
settings = Settings()  # type: ignore
