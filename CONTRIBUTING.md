# Contributing to RailETA

For this private team's repository, use [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md) as
the authoritative access, branch, checkpoint, and setup guide. The current demo
and its limitations are documented in [HISTORICAL_PROFILE_RESULTS.md](HISTORICAL_PROFILE_RESULTS.md).

Thank you for considering contributing to RailETA! This document provides guidelines for contributing to the project.

---

## Code of Conduct

- Be respectful and professional
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect different viewpoints and experiences

---

## How to Contribute

### Reporting Bugs

Before creating a bug report:
1. Check if the bug has already been reported in Issues
2. Verify you're using the latest version
3. Test with a clean installation

When reporting a bug, include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Error messages and logs
- Screenshots if applicable

### Suggesting Features

Feature requests are welcome! Include:
- Clear description of the feature
- Use case: who needs it and why
- How it fits with the project goals
- Possible implementation approach (if you have ideas)

### Pull Requests

1. **Clone the private repository after accepting your invitation**
   ```bash
   git clone https://github.com/Aryaa2020/raileta.git
   cd raileta
   ```

2. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

3. **Make your changes**
   - Follow the code style guidelines below
   - Add tests for new features
   - Update documentation

4. **Test your changes**
   ```bash
   # Django backend tests
   python manage.py test tests -v 1
   
   # Frontend tests
   cd frontend/passenger-ui
   npm run build
   ```

5. **Commit with clear messages**
   ```bash
   git commit -m "feat: add loop prediction visualization"
   git commit -m "fix: correct confidence interval calculation"
   git commit -m "docs: update API documentation for new endpoint"
   ```

   Use conventional commits format:
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation only
   - `style:` - Code style changes (formatting)
   - `refactor:` - Code refactoring
   - `test:` - Adding tests
   - `chore:` - Maintenance tasks

6. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   
   Then create a Pull Request on GitHub with:
   - Clear title and description
   - Link to related issues
   - Screenshots/demos if applicable
   - Checklist of changes

---

## Development Setup

See [SETUP.md](SETUP.md) for detailed development environment setup.

Quick start:
```bash
# Django backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python -m uvicorn django_service.asgi:application --reload --port 8000

# Frontend
cd frontend/passenger-ui
npm install
npm run dev
```

---

## Code Style Guidelines

### Python (Backend)

- Follow [PEP 8](https://pep8.org/)
- Use [Black](https://black.readthedocs.io/) for formatting
- Maximum line length: 100 characters
- Use type hints where possible

```python
# Good
def predict_eta(
    train_number: str, 
    current_delay: float
) -> Dict[str, any]:
    """Predict ETA for a train.
    
    Args:
        train_number: Train identification number
        current_delay: Current delay in minutes
        
    Returns:
        Dictionary with predictions
    """
    pass

# Format with Black
black raileta_api django_service tests
```

- Docstrings: Use Google style
- Imports: Group by standard library, third-party, local
- Naming:
  - Functions/variables: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`

### JavaScript/React (Frontend)

- Follow [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript)
- Use ES6+ features
- Functional components with hooks (not class components)
- Prop types or TypeScript

```javascript
// Good
const StationCard = ({ station, onSelect }) => {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className="station-card">
      {/* ... */}
    </div>
  );
};

// Format with Prettier (automatic in Vite)
```

- Components: PascalCase files (`StationCard.jsx`)
- Utilities: camelCase files (`apiClient.js`)
- Use meaningful names: `isLoading` not `flag`

### Git Commit Messages

```
<type>(<scope>): <subject>

<body>

<footer>
```

Example:
```
feat(models): add loop prediction classifier

Implemented binary classifier to predict train holds for overtaking.
Uses train priority, following trains, and station loop availability.

Closes #42
```

---

## Project Structure Guidelines

### Adding a New Backend Endpoint

1. Define or update the request/response contract in `raileta_api/contracts.py`
2. Add the Django view in `raileta_api/views.py` and URL in `raileta_api/urls.py`
3. Update API documentation in `API.md`
4. Add tests in `tests/`

### Adding a New Frontend Component

1. Create component file in `frontend/*/src/components/`
2. Follow existing component patterns
3. Add to relevant parent component
4. Update component README if significant

### Adding a New Model Feature

1. Add feature engineering in `raileta_api/forecasting.py` or the model service
2. Update feature list in docstrings
3. Retrain models and verify improvement
4. Document feature importance

---

## Testing

### Backend Tests

```bash
# Run all tests
python manage.py test tests -v 1

# Run with coverage
pytest --cov=raileta_api

# Run specific test file
python manage.py test tests.test_django_api -v 2
```

Test structure:
```python
def test_eta_prediction():
    """Test basic ETA prediction"""
    predictor = ETAPredictor()
    result = predictor.predict(sample_features)
    
    assert 'predictions' in result
    assert len(result['predictions']) > 0
```

### Frontend Tests

```bash
cd frontend/passenger-ui
npm test
```

---

## Documentation

Update documentation when:
- Adding new features
- Changing API endpoints
- Modifying configuration
- Updating dependencies

Documentation files:
- `README.md` - Overview and quick start
- `SETUP.md` - Detailed setup instructions
- `API.md` - API reference
- Component READMEs in each frontend directory

Use clear, concise language. Include examples.

---

## Review Process

PRs will be reviewed for:
1. **Functionality** - Does it work as intended?
2. **Code quality** - Is it clean and maintainable?
3. **Tests** - Are there adequate tests?
4. **Documentation** - Is it documented?
5. **Performance** - Any performance impacts?

Expect feedback and iteration. All PRs need at least one approval.

---

## Priority Areas for Contribution

High-impact areas where contributions are especially welcome:

### Data Collection
- Improved NTES scraper (more robust parsing)
- Support for additional corridors
- Better error handling for API failures

### Model Improvements
- Additional feature engineering
- Hyperparameter tuning
- Alternative algorithms comparison
- Model interpretability enhancements

### Frontend
- Mobile app (React Native)
- Accessibility improvements (WCAG compliance)
- Offline support (PWA)
- Additional visualizations

### Infrastructure
- Docker containerization
- Kubernetes deployment configs
- CI/CD pipeline
- Automated testing

### Documentation
- Video tutorials
- Architecture diagrams
- Deployment guides for different platforms
- Translation to Hindi/regional languages

---

## Questions?

- Open an issue for questions
- Join discussions in Issues
- Email: team@raileta.example.com

---

Thank you for contributing to RailETA! 🚂
