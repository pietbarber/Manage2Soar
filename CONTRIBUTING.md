## 🤝 Contributing

We welcome contributions! This project is designed for soaring clubs worldwide to fork and customize for their needs.

### Quick Start for Contributors

1. **Fork and clone** the repository
2. **Run the setup script** for automatic environment setup:
   ```bash
   ./infrastructure/scripts/setup-dev.sh
   ```
   Or manually:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   pip install pre-commit && pre-commit install
   python manage.py migrate
   ```

### Development Requirements

🔒 **Security Tools Required**: This project uses automated security scanning:
- **Pre-commit hooks**: Run `pre-commit install` (required for development)
- **Security scans**: Run automatically on every commit (Bandit, Safety, secret detection)
- **Code formatting**: Automatic formatting with Black, isort, django-upgrade

### Contribution Process

1. **Create an issue** for major changes to discuss approach
2. **Fork the repository** and create a feature branch
3. **Make your changes** - pre-commit hooks will run security scans automatically
4. **Write tests** - maintain comprehensive test coverage
5. **Submit a pull request** - GitHub Actions will run additional security checks
6. **Address feedback** from code review and security scans

### Security & Quality Standards

- All commits are scanned for security vulnerabilities
- High-severity security issues will block PR merges
- Code formatting is automatically applied and enforced
- Test coverage should be maintained or improved

### For Forkers

This project is designed to be fork-friendly for other soaring clubs:
- ✅ No external dependencies or secrets required
- ✅ GitHub Actions work automatically
- ✅ Comprehensive documentation and setup scripts
- ✅ Modular architecture for customization

For questions or support, please create an issue or contact the maintainers.
