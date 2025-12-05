# Magnification - Job Search Application Project Structure

## Overview
A hybrid Python project combining a job scraping backend with a Flask web frontend. Utilizes custom libraries for LLM integration and logging.

---

## Directory Structure

```
magnificiation/
│
├── utils/                             # Main Python utilities container
│   ├── backend/                       # Backend scraping and Flask API
│   │   ├── scrapers/                  # Job scraping modules
│   │   ├── processors/                # Data processing and enrichment
│   │   ├── routes/                    # Flask API route blueprints
│   │   ├── database/                  # Database models and operations
│   │   ├── services/                  # Business logic layer
│   │   └── tests/                     # Backend unit tests
│   ├── frontend/                      # Frontend assets and templates
│   │   ├── templates/                 # Jinja2 HTML templates
│   │   └── static/                    # Static web assets
│   │       ├── css/
│   │       ├── js/
│   │       │   ├── components/       # Reusable UI components
│   │       │   ├── pages/            # Page-specific scripts
│   │       │   ├── utils/            # Utility functions
│   │       │   ├── lib/              # Third-party and custom libraries
│   │       │   ├── config/           # Configuration files
│   │       │   └── services/         # API interaction services
│   │       └── images/
│   ├── libs/                          # Custom shared libraries
│   │   └── llm/                       # Local LLM integration library
│   └── scripts/                       # Utility scripts
│
├── logs/                              # Application logs storage
│
├── data/                              # Data storage
│
├── config/                            # User and environment configurations
│
├── docs/                              # Documentation
│
├── app.py                             # Main entry point of the application
├── README.md                          # Project overview and setup instructions
├── requirements.txt                   # Python dependencies
├── .env.example                       # Environment variables template
└── .gitignore                         # Git ignore rules
```

---

## Key Components Explained

### Main Structure
- **utils/**: Main container for all Python code, libraries, scripts, and configuration
  - **backend/**: Job scraping, processing, and Flask API routes
    - **scrapers/**: Job collection modules
    - **processors/**: Data validation and enrichment
    - **routes/**: Flask API endpoint blueprints
    - **database/**: ORM models and data persistence
    - **services/**: Business logic layer
    - **tests/**: Backend unit tests
  - **frontend/**: Frontend assets and templates
    - **templates/**: Jinja2 HTML templates
    - **static/**: Static web assets
      - **css/**: Stylesheets
      - **js/**: JavaScript files organized into subdirectories for maintainability
        - **components/**: Reusable UI components (e.g., modals, buttons, form elements)
        - **pages/**: Page-specific scripts (e.g., home.js, search.js, profile.js)
        - **utils/**: Utility functions (e.g., helpers, formatters, validators)
        - **lib/**: Third-party libraries and custom JavaScript libraries
        - **config/**: Configuration files and constants
        - **services/**: API interaction services and data fetching logic
      - **images/**: Image assets
  - **libs/**: Custom shared libraries (logger wrapper and LLM integration)
  - **scripts/**: Utility scripts for development and maintenance
  - **config/**: Centralized configuration management

### Storage Directories
- **logs/**: All application logs are stored here
- **data/**: Persistent data storage (databases, cached data, etc.)

### Documentation & Configuration
- **docs/**: Project documentation
- **README.md**, **requirements.txt**, **.env.example**, **.gitignore**: Root-level project files

---

## Dependencies Structure

```
magnificiation/
├── utils/                             # All Python code
│   ├── Backend Dependencies (scraping, processing)
│   ├── Frontend Dependencies (Flask, WTF)
│   ├── Shared Dependencies (SQLAlchemy, requests)
│   └── Custom Libraries (libs/)
├── logs/                              # Application logs
└── data/                              # Persistent data storage
```

---

## Environment Setup

- Python 3.9+
- Package manager: uv
- Virtual environment: Managed by uv
- Environment variables: `.env` file
- Database: SQLite (dev)

---

## Notes

1. **Centralized Python Code**: All Python functionality contained in `utils/` for clean separation from data and logs
2. **Organized Storage**: Dedicated `logs/` and `data/` directories at root level for easy access and backup
3. **Frontend Organization**: Routes separated for clarity, templates flattened for simplicity
4. **Custom Libs**: Centralized in `utils/libs/` for consistent usage across backend and frontend
5. **Configuration**: Externalized configuration for different environments
6. **Scripts**: Utility scripts for common development tasks
7. **JavaScript Organization**: JavaScript files are organized into subdirectories within `static/js/` to manage complexity as the application expands, separating reusable components, page-specific scripts, utilities, libraries, configurations, and API services
