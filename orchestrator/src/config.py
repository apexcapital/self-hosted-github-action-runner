"""Configuration management for the orchestrator."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # GitHub Configuration
    github_token: str = Field("", description="GitHub Personal Access Token")
    github_org: Optional[str] = Field(
        None, description="GitHub organization (optional)"
    )
    github_repo: Optional[str] = Field(None, description="GitHub repository (optional)")

    # Runner Configuration
    runner_image: str = Field(
        "ghcr.io/apexcapital/runner:latest", description="Docker image for runners"
    )
    runner_version: str = Field("2.325.0", description="GitHub Actions runner version")

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
    runner_labels: list[str] = Field(
        default=["docker-dind", "linux", "x64", "self-hosted", "orchestrated"],
        description="Labels to assign to runners",
    )

    # Logging Configuration
    log_level: str = Field("INFO", description="Logging level")
    structured_logging: bool = Field(True, description="Enable structured logging")

    # Orchestrator Identification
    orchestrator_id: str = Field(
        "apex-runner-orchestrator",
        description="Unique identifier for this orchestrator instance",
    )
    orchestrator_version: str = Field(
        "1.0.0", description="Version of the orchestrator"
    )

    # Redis Configuration (optional for distributed setups)
    redis_url: Optional[str] = Field(
        None, description="Redis URL for distributed coordination"
    )

    class Config:
        env_file = ".env"
        env_prefix = "ORCHESTRATOR_"


# Global settings instance
# Fields have defaults via Field(), Pydantic handles this automatically
settings = Settings()  # type: ignore # Pydantic Settings with defaults
