from flask import Flask, send_file, send_from_directory

# Initialize database on import
from utils.backend.database import init_database

from utils.backend.routes.config_routes import config_bp
from utils.backend.routes.scrape_routes import scrape_bp
from utils.backend.routes.job_routes import job_bp
from utils.backend.routes.llm_routes import llm_bp

application = Flask(__name__, static_folder='utils/frontend/static', template_folder='utils/frontend/templates')
application.register_blueprint(config_bp)
application.register_blueprint(scrape_bp)
application.register_blueprint(job_bp)
application.register_blueprint(llm_bp)

# Initialize database tables
init_database()

@application.route('/')
def index():
    return send_file('utils/frontend/templates/index.html')

@application.route('/parts/<path:filename>')
def serve_parts(filename):
    return send_from_directory('utils/frontend/templates/parts', filename)

@application.route('/primary/<path:filename>')
def serve_primary(filename):
    return send_from_directory('utils/frontend/templates/primary', filename)

if __name__ == '__main__':
    application.run(debug=True)