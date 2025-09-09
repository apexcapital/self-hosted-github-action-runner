#!/usr/bin/env bash
set -euo pipefail

# GitHub Actions Runner Orchestrator Setup Script
# This script helps you set up the enhanced orchestrator system

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "\n${BLUE}===============================================${NC}"
    echo -e "${BLUE}  GitHub Actions Runner Orchestrator 2.0${NC}"
    echo -e "${BLUE}===============================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running. Please start Docker first."
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Setup environment file
setup_environment() {
    print_info "Setting up environment configuration..."
    
    if [[ ! -f .env.example ]]; then
        print_error "Example environment file not found"
        exit 1
    fi
    
    if [[ ! -f .env ]]; then
        cp .env.example .env
        print_success "Created .env from example"
    else
        print_warning ".env already exists, skipping creation"
    fi
    
    # Prompt for GitHub token if not set
    if ! grep -q "^ORCHESTRATOR_GITHUB_TOKEN=" .env 2>/dev/null || grep -q "^ORCHESTRATOR_GITHUB_TOKEN=your_github_personal_access_token_here" .env 2>/dev/null; then
        echo
        print_info "GitHub Personal Access Token is required"
        echo "You can create one at: https://github.com/settings/personal-access-tokens/new"
        echo "Required permissions:"
        echo "  - For repositories: repo (Full control)"
        echo "  - For organizations: admin:org (Read/Write access)"
        echo
        read -p "Enter your GitHub Personal Access Token: " -s github_token
        echo
        
        if [[ -n "$github_token" ]]; then
            sed -i.bak "s/^ORCHESTRATOR_GITHUB_TOKEN=.*/ORCHESTRATOR_GITHUB_TOKEN=$github_token/" .env
            rm -f .env.bak
            print_success "GitHub token configured"
        else
            print_warning "No token provided. Please edit .env manually"
        fi
    fi
    
    # Prompt for organization or repository
    if ! grep -q "^ORCHESTRATOR_GITHUB_ORG=" .env 2>/dev/null || grep -q "^ORCHESTRATOR_GITHUB_ORG=your-github-organization" .env 2>/dev/null; then
        if ! grep -q "^ORCHESTRATOR_GITHUB_REPO=" .env 2>/dev/null || grep -q "^ORCHESTRATOR_GITHUB_REPO=owner/repository-name" .env 2>/dev/null; then
            echo
            print_info "Choose GitHub scope:"
            echo "1) Organization-wide runners"
            echo "2) Repository-specific runners"
            read -p "Enter choice (1 or 2): " choice
            
            case $choice in
                1)
                    read -p "Enter your GitHub organization name: " org_name
                    if [[ -n "$org_name" ]]; then
                        sed -i.bak "s/^ORCHESTRATOR_GITHUB_ORG=.*/ORCHESTRATOR_GITHUB_ORG=$org_name/" .env
                        rm -f .env.bak
                        print_success "Organization configured: $org_name"
                    fi
                    ;;
                2)
                    read -p "Enter repository (format: owner/repo): " repo_name
                    if [[ -n "$repo_name" ]]; then
                        sed -i.bak "s/^ORCHESTRATOR_GITHUB_REPO=.*/ORCHESTRATOR_GITHUB_REPO=$repo_name/" .env
                        rm -f .env.bak
                        print_success "Repository configured: $repo_name"
                    fi
                    ;;
                *)
                    print_warning "Invalid choice. Please edit .env manually"
                    ;;
            esac
        fi
    fi
}

# Build and deploy
deploy_orchestrator() {
    print_info "Building and deploying orchestrator..."
    
    # Build the orchestrator image
    print_info "Building orchestrator image..."
    if docker compose build; then
        print_success "Orchestrator image built successfully"
    else
        print_error "Failed to build orchestrator image"
        exit 1
    fi
    
    # Build the enhanced runner image
    print_info "Building enhanced runner image..."
    if docker build -f Dockerfile -t ghcr.io/apexcapital/runner:latest .; then
        print_success "Enhanced runner image built successfully"
    else
        print_error "Failed to build runner image"
        exit 1
    fi
    
    # Deploy the orchestrator
    print_info "Starting orchestrator services..."
    if docker compose up -d; then
        print_success "Orchestrator services started"
    else
        print_error "Failed to start orchestrator services"
        exit 1
    fi
}

# Wait for services to be ready
wait_for_services() {
    print_info "Waiting for services to be ready..."
    
    # Wait for orchestrator to be healthy
    for i in {1..30}; do
        if curl -s http://localhost:8080/health > /dev/null 2>&1; then
            print_success "Orchestrator is ready"
            break
        fi
        
        if [[ $i -eq 30 ]]; then
            print_error "Orchestrator failed to start within 5 minutes"
            print_info "Check logs with: docker logs orchestrator"
            exit 1
        fi
        
        echo -n "."
        sleep 10
    done
}

# Show status
show_status() {
    print_info "Checking orchestrator status..."
    
    # Get status from API
    if status=$(curl -s http://localhost:8080/api/v1/status 2>/dev/null); then
        echo
        print_success "Orchestrator Status:"
        echo "$status" | python3 -m json.tool 2>/dev/null || echo "$status"
    else
        print_warning "Could not retrieve status from API"
    fi
    
    echo
    print_info "Service URLs:"
    echo "  Orchestrator API: http://localhost:8080"
    echo "  API Documentation: http://localhost:8080/docs"
    echo "  Prometheus Metrics: http://localhost:9091"
    echo "  Redis: localhost:6379"
    
    echo
    print_info "Useful Commands:"
    echo "  View logs: docker logs -f orchestrator"
    echo "  Stop services: docker compose down"
    echo "  Restart services: docker compose restart"
    echo "  Check status: curl http://localhost:8080/api/v1/status | jq"
}

# Cleanup function
cleanup_old_system() {
    print_info "Looking for old runner containers to clean up..."
    
    # Stop old-style runners
    old_runners=$(docker ps -q --filter "name=*runner*" --filter "label!=managed-by=runner-orchestrator" 2>/dev/null || true)
    if [[ -n "$old_runners" ]]; then
        print_warning "Found old runner containers, stopping them..."
        docker stop $old_runners || true
        docker rm $old_runners || true
        print_success "Old runner containers cleaned up"
    else
        print_success "No old runner containers found"
    fi
}

# Main setup flow
main() {
    print_header
    
    echo "This script will set up the GitHub Actions Runner Orchestrator 2.0"
    echo "The orchestrator provides dynamic, auto-scaling runner management."
    echo
    read -p "Continue with setup? (y/N): " confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Setup cancelled"
        exit 0
    fi
    
    check_prerequisites
    cleanup_old_system
    setup_environment
    deploy_orchestrator
    wait_for_services
    show_status
    
    echo
    print_success "🎉 Setup completed successfully!"
    echo
    print_info "Next steps:"
    echo "1. Review the configuration in .env"
    echo "2. Check the orchestrator logs: docker logs -f orchestrator"
    echo "3. Monitor runners at: http://localhost:8080/docs"
    echo "4. Update your GitHub Actions workflows to use 'self-hosted,orchestrated' labels"
    echo
    print_info "For more information, see README.md"
}

# Handle script arguments
case "${1:-}" in
    "cleanup")
        print_header
        print_info "Cleaning up orchestrator deployment..."
        docker compose down --volumes
        docker rmi ghcr.io/apexcapital/runner:latest 2>/dev/null || true
        print_success "Cleanup completed"
        ;;
    "status")
        show_status
        ;;
    "logs")
        docker logs -f orchestrator
        ;;
    "restart")
        print_info "Restarting orchestrator services..."
        docker compose restart
        print_success "Services restarted"
        ;;
    *)
        main
        ;;
esac
