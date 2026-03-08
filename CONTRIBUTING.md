# Contributing to LangGraph Terminal UI

Thank you for your interest in contributing to LangGraph Terminal UI! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Submitting Changes](#submitting-changes)
- [Style Guidelines](#style-guidelines)
- [Testing Guidelines](#testing-guidelines)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what is best for the community
- Show empathy towards other community members

## Getting Started

### Prerequisites

- Python 3.12 or higher
- Git
- Basic knowledge of Python, LangChain, and LangGraph

### Development Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/langgraph-terminal-ui.git
   cd langgraph-terminal-ui
   ```
3. Create a virtual environment:
   ```bash
   py -3.12 -m venv .venv312
   .venv312\Scripts\activate
   ```
4. Install dependencies with development tools:
   ```bash
   pip install -e ".[dev]"
   ```
5. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Making Changes

### Code Style

- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Write docstrings for all functions and classes
- Keep functions focused and small
- Use meaningful variable and function names

### Formatting

We use `ruff` for linting and formatting:

```bash
# Check code style
ruff check src/

# Format code
ruff format src/

# Fix linting issues
ruff check --fix src/
```

### Type Checking

We use `mypy` for type checking:

```bash
mypy src/
```

### Documentation

- Update the README.md if you change user-facing features
- Add docstrings to new functions and classes
- Keep comments clear and concise
- Remove commented-out code

## Testing Guidelines

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_config_roundtrip.py

# Run with coverage
pytest --cov=src/langgraph_terminal --cov-report=html

# Run with verbose output
pytest -v
```

### Writing Tests

- Write tests for new features
- Write tests for bug fixes
- Keep tests simple and focused
- Use descriptive test names
- Mock external dependencies (APIs, file system, etc.)

Example:

```python
def test_set_temperature_valid():
    """Test setting a valid temperature value."""
    runtime = ApplicationRuntime()
    result = runtime.set_temperature("0.5")
    assert "Temperature updated to 0.5" in result
    assert runtime.config.temperature == 0.5
```

### Test Coverage

We aim for high test coverage. Before submitting, ensure:

- All new code has tests
- No test failures
- Coverage is maintained or improved

## Submitting Changes

### Commit Messages

Follow these guidelines for commit messages:

- Use the imperative mood ("Add" not "Added")
- Keep the first line under 50 characters
- Reference issues with `#123` format
- Provide more detail in the body if needed

Example:
```
Add support for custom reasoning profiles

Fixes #45

- Added custom reasoning profile configuration
- Updated CLI command for setting profiles
- Added tests for new functionality
```

### Pull Request Process

1. Update your branch with the latest main:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

3. Create a Pull Request on GitHub

4. Fill out the PR template:
   - Describe the changes
   - Link to related issues
   - List testing done
   - Add screenshots if UI changes

### Review Process

- Maintainers will review your PR
- Address review feedback promptly
- Tests must pass before merge
- Code must pass linting and type checking

## Style Guidelines

### Python

- Use `f-strings` for string formatting
- Prefer list comprehensions over `map`/`filter`
- Use context managers for resources (`with` statements)
- Handle exceptions appropriately
- Avoid global state

### Documentation

- Use clear, concise language
- Provide examples for complex features
- Keep README.md up to date
- Document breaking changes in CHANGELOG

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

- Clear description of the problem
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details (OS, Python version)
- Error messages or logs

### Feature Requests

For feature requests, please include:

- Clear description of the feature
- Use case or problem it solves
- Possible implementation approach
- Alternatives considered

### Questions

For questions about usage:

- Check the README.md first
- Search existing issues
- Provide context about what you're trying to do

## Getting Help

- Open an issue for bugs or feature requests
- Start a discussion for questions
- Check existing documentation
- Review example code in the repository

## Recognition

Contributors will be acknowledged in:
- CONTRIBUTORS.md file
- Release notes
- Project documentation

Thank you for contributing to LangGraph Terminal UI! 🚀
