import os

from flask import Flask, send_file

# Initialize database on import
from utils.backend.database import init_database

# Absolute path to this file's directory so the app serves the right files
# regardless of the current working directory (e.g. when run from a git worktree).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(BASE_DIR, 'utils/frontend/templates/index.html')

from utils.backend.routes.config_routes import config_bp
from utils.backend.routes.scrape_routes import scrape_bp
from utils.backend.routes.job_routes import job_bp
from utils.backend.routes.llm_routes import llm_bp
from utils.backend.routes.options_routes import options_bp
from utils.backend.routes.profile_routes import profile_bp
from utils.backend.routes.recommend_routes import recommend_bp
from utils.backend.routes.documents_routes import documents_bp

application = Flask(__name__, static_folder='utils/frontend/static', template_folder='utils/frontend/templates')
application.register_blueprint(config_bp)
application.register_blueprint(scrape_bp)
application.register_blueprint(job_bp)
application.register_blueprint(llm_bp)
application.register_blueprint(options_bp)
application.register_blueprint(profile_bp)
application.register_blueprint(recommend_bp)
application.register_blueprint(documents_bp)

# Initialize database tables
init_database()

# Initialize Logger
from utils.LocalLLM.utils.logger import LoggerWrapper
LoggerWrapper()

@application.route('/')
def index():
    return send_file(INDEX_HTML)

if __name__ == '__main__':
    # PORT env override lets the dev server run alongside other instances
    # (e.g. a worktree preview next to the main checkout). Default 13374.
    # FLASK_DEBUG=0 disables the debugger/auto-reloader — used by the systemd
    # service, where the reloader's forking would fight the service supervisor.
    debug = os.environ.get('FLASK_DEBUG', '1') != '0'
    application.run(debug=debug, port=int(os.environ.get('PORT', 13374)))