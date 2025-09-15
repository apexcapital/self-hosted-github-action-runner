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
    
    # Build the custom runner image from runner-image/Dockerfile
    if [[ -f runner-image/Dockerfile ]]; then
        print_info "Building custom runner image apex-runner:local..."
        # Build from repository root so files like ./daemon.json (repo root)
        # are available to the Docker build via the build context.
        if docker build -t apex-runner:local -f runner-image/Dockerfile .; then
            print_success "Custom runner image built successfully"
        else
            print_error "Failed to build custom runner image"
            exit 1
        fi
    else
        print_warning "No runner-image/Dockerfile found, assuming ORCHESTRATOR_RUNNER_IMAGE is set"
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

# Deregister orchestrated runners from GitHub (organization or repo scope)
deregister_github_runners() {
    print_info "Deregistering orchestrated runners from GitHub..."

    # Load only the specific env vars we need (safe parsing, allows comments/complex .env)
    if [[ -f .env ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            # skip comments and blank lines
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$line" ]] && continue

            key="${line%%=*}"
            val="${line#*=}"

            case "$key" in
                ORCHESTRATOR_GITHUB_TOKEN|ORCHESTRATOR_GITHUB_ORG|ORCHESTRATOR_GITHUB_REPO|ORCHESTRATOR_RUNNER_PREFIX)
                    # trim leading/trailing whitespace
                    val="${val#${val%%[![:space:]]*}}"
                    val="${val%${val##*[![:space:]]}}"

                    # remove surrounding single or double quotes
                    first_char="${val:0:1}"
                    last_char="${val:$((${#val}-1)):1}"
                    if [[ ( "$first_char" == '"' && "$last_char" == '"' ) || ( "$first_char" == "'" && "$last_char" == "'" ) ]]; then
                        val="${val:1:$((${#val}-2))}"
                    fi

                    export "$key"="$val"
                    ;;
            esac
        done < .env
    fi

    # Determine API base and auth (use safe expansions to avoid set -u failures)
    if [[ -n "${ORCHESTRATOR_GITHUB_REPO:-}" && "${ORCHESTRATOR_GITHUB_REPO:-}" != "owner/repository-name" ]]; then
        # repo scope
        API_BASE="https://api.github.com/repos/${ORCHESTRATOR_GITHUB_REPO:-}"
    elif [[ -n "${ORCHESTRATOR_GITHUB_ORG:-}" && "${ORCHESTRATOR_GITHUB_ORG:-}" != "your-github-organization" ]]; then
        # org scope
        API_BASE="https://api.github.com/orgs/${ORCHESTRATOR_GITHUB_ORG:-}"
    else
        print_warning "Neither ORCHESTRATOR_GITHUB_REPO nor ORCHESTRATOR_GITHUB_ORG set in .env; skipping GitHub deregistration"
        return
    fi

    if [[ -z "${ORCHESTRATOR_GITHUB_TOKEN:-}" || "${ORCHESTRATOR_GITHUB_TOKEN}" == "your_github_personal_access_token_here" ]]; then
        print_warning "No valid ORCHESTRATOR_GITHUB_TOKEN found in .env; skipping GitHub deregistration"
        return
    fi

    PREFIX="${ORCHESTRATOR_RUNNER_PREFIX:-orchestrated}"

    # Fetch runners
    runners_response=$(curl -s -H "Authorization: token ${ORCHESTRATOR_GITHUB_TOKEN}" "${API_BASE}/actions/runners")
    runner_ids=$(echo "$runners_response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(' '.join([str(r['id'])+','+r['name'] for r in data.get('runners',[])]))")

    if [[ -z "$runner_ids" ]]; then
        print_success "No runners found in GitHub for deregistration"
        return
    fi

    # Iterate over runners and delete those matching the prefix
    IFS=' ' read -r -a arr <<< "$runner_ids"
    deleted=0
    for item in "${arr[@]}"; do
        id=${item%%,*}
        name=${item#*,}
        if [[ "$name" == ${PREFIX}* ]]; then
            print_info "Deregistering runner: $name (id: $id)"
            # Attempt delete
            del_resp=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE -H "Authorization: token ${ORCHESTRATOR_GITHUB_TOKEN}" "${API_BASE}/actions/runners/${id}")
            if [[ "$del_resp" == "204" ]]; then
                print_success "Deregistered $name"
                deleted=$((deleted+1))
            else
                print_warning "Failed to deregister $name (http status $del_resp)"
            fi
        fi
    done

    print_info "Deregistered $deleted orchestrated runners (if any)"
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
            # Deregister orchestrated runners from GitHub first
            deregister_github_runners

            # Stop orchestrator services first so it doesn't recreate runners
            print_info "Stopping orchestrator services (docker compose down)…"
            docker compose down --remove-orphans --volumes || true

            # If the orchestrator container still exists (compose mismatch or started elsewhere), stop/remove it explicitly
            orch_containers=$(docker ps -a -q --filter "label=component=orchestrator" --filter "label=managed-by=runner-orchestrator" 2>/dev/null || true)
            if [[ -z "$orch_containers" ]]; then
                # Try by common container name
                if docker ps -a --format '{{.Names}}' | grep -q '^orchestrator$'; then
                    orch_containers=$(docker ps -a -q --filter "name=^orchestrator$")
                fi
            fi

            if [[ -n "$orch_containers" ]]; then
                print_warning "Found running orchestrator container(s); stopping and removing explicitly..."
                docker stop $orch_containers || true
                docker rm -v $orch_containers || true
                print_success "Orchestrator container(s) stopped and removed"
            else
                print_info "No standalone orchestrator container found after compose down"
            fi

            # Then stop/remove runner containers managed by the orchestrator (by label)
            print_info "Stopping and removing orchestrated runner containers..."
            managed_containers=$(docker ps -a -q --filter "label=managed-by=runner-orchestrator" 2>/dev/null || true)
            if [[ -n "$managed_containers" ]]; then
                docker stop $managed_containers || true
                docker rm -v $managed_containers || true

                # Remove any named volumes created for runners (work volumes)
                managed_vols=$(docker volume ls -q --filter "label=managed-by=runner-orchestrator" 2>/dev/null || true)
                if [[ -n "$managed_vols" ]]; then
                    docker volume rm $managed_vols || true
                fi

                print_success "Stopped and removed orchestrated runner containers and volumes"
            else
                print_success "No orchestrated runner containers found"
            fi

            # Remove locally built runner image if present
            docker rmi apex-runner:local 2>/dev/null || true
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
