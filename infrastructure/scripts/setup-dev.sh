#!/bin/bash
# Development Environment Setup Script for Manage2Soar
# Run this after cloning to set up a complete development environment

set -e  # Exit on any error

echo "🚀 Setting up Manage2Soar development environment..."
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Install development tools
echo "🛡️ Installing security and development tools..."
pip install pre-commit

# Set up pre-commit hooks
echo "🎣 Installing pre-commit hooks..."
pre-commit install

# Verify security tools are working
echo "🔍 Verifying security tools..."
bandit --version
echo "✅ Bandit security scanner ready"

# Apply database migrations
echo "🗄️ Applying database migrations..."
python manage.py migrate

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Create a superuser: python manage.py createsuperuser"
echo "2. Start the development server: python manage.py runserver 127.0.0.1:8001"
echo "3. Visit http://127.0.0.1:8001 to see the application"
echo ""
echo "💡 Security features enabled:"
echo "   - Pre-commit hooks will run security scans on every commit"
echo "   - GitHub Actions will run additional security checks on PRs"
echo "   - Run 'pre-commit run --all-files' to test all security checks"
echo ""
echo "📚 For more information, see:"
echo "   - README.md for project overview"
echo "   - docs/security-workflow.md for security details"
echo "   - docs/workflows/ for business process documentation"
