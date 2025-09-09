#!/usr/bin/env bash
set -euo pipefail

# GitHub Actions Runner Orchestrator - Development Setup
# This script sets up the development environment and validates the installation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}===============================================${NC}"
    echo -e "${BLUE}  GitHub Actions Runner Orchestrator 2.0${NC}"
    echo -e "${BLUE}     Development Environment Setup${NC}"
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

# Check Python version
check_python() {
    print_info "Checking Python version..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    
    print_info "Found Python $PYTHON_VERSION"
    
    if [[ $MAJOR -lt 3 ]] || [[ $MAJOR -eq 3 && $MINOR -lt 9 ]]; then
        print_error "Python 3.9+ is required, found $PYTHON_VERSION"
        exit 1
    fi
    
    if [[ $MAJOR -eq 3 && $MINOR -ge 13 ]]; then
        print_warning "Using Python 3.13+. Using compatible package versions."
    fi
    
    print_success "Python version is compatible"
}

# Setup virtual environment
setup_venv() {
    print_info "Setting up virtual environment..."
    
    if [[ ! -d ".venv" ]]; then
        python3 -m venv .venv
        print_success "Virtual environment created"
    else
        print_info "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    source .venv/bin/activate
    print_success "Virtual environment activated"
    
    # Upgrade pip and build tools
    print_info "Upgrading pip and build tools..."
    pip install --upgrade pip setuptools wheel
    print_success "Build tools updated"
}

# Install dependencies
install_dependencies() {
    print_info "Installing Python dependencies..."
    
    if pip install -r requirements.txt; then
        print_success "Dependencies installed successfully"
    else
        print_error "Failed to install dependencies"
        print_info "This might be due to Python 3.13 compatibility issues"
        print_info "Try using Python 3.11 or 3.12 if available"
        exit 1
    fi
}

# Validate installation
validate_installation() {
    print_info "Validating installation..."
    
    if python validate.py; then
        print_success "Installation validation passed"
    else
        print_error "Installation validation failed"
        exit 1
    fi
}

# Create sample configuration
create_sample_config() {
    print_info "Creating sample configuration..."
    
    if [[ ! -f ".env.example" ]]; then
        cat > .env.example << 'EOF'
# GitHub Configuration - REQUIRED
ORCHESTRATOR_GITHUB_TOKEN=your_github_personal_access_token_here

# GitHub scope - choose ONE of the following:
ORCHESTRATOR_GITHUB_ORG=your-organization-name  # For organization-wide runners
# ORCHESTRATOR_GITHUB_REPO=owner/repository-name  # For repository-specific runners

# Runner Configuration
ORCHESTRATOR_RUNNER_IMAGE=ghcr.io/apexcapital/runner:latest
ORCHESTRATOR_RUNNER_VERSION=2.325.0

# Scaling Configuration
ORCHESTRATOR_MIN_RUNNERS=2
ORCHESTRATOR_MAX_RUNNERS=10
ORCHESTRATOR_SCALE_UP_THRESHOLD=3
ORCHESTRATOR_SCALE_DOWN_THRESHOLD=1
ORCHESTRATOR_IDLE_TIMEOUT=300

# Monitoring Configuration
ORCHESTRATOR_POLL_INTERVAL=30
ORCHESTRATOR_LOG_LEVEL=INFO
ORCHESTRATOR_STRUCTURED_LOGGING=true

# Docker Configuration
ORCHESTRATOR_RUNNER_NETWORK=runner-network
EOF
        print_success "Sample configuration created (.env.example)"
    else
        print_info "Sample configuration already exists"
    fi
}

# Run development server
run_dev_server() {
    print_info "Starting development server..."
    print_warning "Make sure to create .env file with your configuration first!"
    print_info "Copy .env.example to .env and edit with your settings"
    echo
    print_info "Server will be available at:"
    echo "  API: http://localhost:8080"
    echo "  Docs: http://localhost:8080/docs"
    echo
    print_info "Press Ctrl+C to stop the server"
    echo
    
    # Check if .env exists
    if [[ ! -f ".env" ]]; then
        print_warning "No .env file found. Using default/test configuration."
        export ORCHESTRATOR_GITHUB_TOKEN="test_token_replace_me"
    fi
    
    python main.py
}

# Show help
show_help() {
    echo "GitHub Actions Runner Orchestrator - Development Setup"
    echo
    echo "Usage: $0 [COMMAND]"
    echo
    echo "Commands:"
    echo "  setup     - Set up development environment (default)"
    echo "  validate  - Validate installation"
    echo "  run       - Run development server"
    echo "  clean     - Clean virtual environment"
    echo "  help      - Show this help message"
    echo
    echo "Examples:"
    echo "  $0              # Setup development environment"
    echo "  $0 validate     # Validate installation"
    echo "  $0 run          # Run development server"
}

# Clean environment
clean_env() {
    print_info "Cleaning development environment..."
    
    if [[ -d ".venv" ]]; then
        rm -rf .venv
        print_success "Virtual environment removed"
    fi
    
    if [[ -f ".env" ]]; then
        rm .env
        print_success "Environment file removed"
    fi
    
    print_success "Environment cleaned"
}

# Main setup flow
main_setup() {
    print_header
    
    check_python
    setup_venv
    install_dependencies
    validate_installation
    create_sample_config
    
    echo
    print_success "🎉 Development environment setup completed!"
    echo
    print_info "Next steps:"
    echo "1. Copy .env.example to .env: cp .env.example .env"
    echo "2. Edit .env with your GitHub token and configuration"
    echo "3. Run the development server: $0 run"
    echo "4. Visit http://localhost:8080/docs for API documentation"
    echo
    print_info "For production deployment, see ../README.md"
}

# Handle script arguments
case "${1:-setup}" in
    "setup")
        main_setup
        ;;
    "validate")
        print_header
        if [[ -d ".venv" ]]; then
            source .venv/bin/activate
        fi
        validate_installation
        ;;
    "run")
        print_header
        if [[ ! -d ".venv" ]]; then
            print_error "Virtual environment not found. Run '$0 setup' first."
            exit 1
        fi
        source .venv/bin/activate
        run_dev_server
        ;;
    "clean")
        print_header
        clean_env
        ;;
    "help"|"-h"|"--help")
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
