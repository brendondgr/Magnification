"""API routes for LLM server control and configuration."""

from flask import Blueprint, jsonify, request
import os
from pathlib import Path
from loguru import logger

# Import LocalLLM utilities
from utils.LocalLLM.utils.config_loader import ConfigLoader, get_all_language_models
from utils.LocalLLM.utils.config_manager import ConfigManager
from utils.LocalLLM.core.application import LocalLMM

llm_bp = Blueprint('llm', __name__, url_prefix='/api')

# Global server state
server_status = 'stopped'  # stopped, starting, running, stopping, error
llm_instance = None  # Global LocalLMM instance

@llm_bp.route('/config', methods=['GET'])
def get_config():
    """Get LLM configuration including models and directories."""
    try:
        loader = ConfigLoader()
        config_data = loader._config
        
        if not config_data:
            return jsonify({'error': 'Configuration not loaded'}), 500
        
        # Return configuration with frontend defaults
        response = {
            'model_directories': config_data.get('model_directories', {}),
            'language_models': config_data.get('language_models', []),
            'voice_models': config_data.get('voice_models', []),
            'frontend_defaults': config_data.get('frontend_defaults', {
                'model': '',
                'streaming': True,
                'context_size': 15,
                'max_tokens': 13,
                'temperature': 0.1,
                'repeat_penalty': 1.2,
                'host': '127.0.0.1',
                'port': 8080,
                'compute_mode': 'auto',
                'gpu_layers': 999,
                'threads': 0,
                'advanced_settings_open': False
            })
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@llm_bp.route('/config', methods=['POST'])
def save_config():
    """Save LLM configuration (frontend defaults)."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Load current config
        loader = ConfigLoader()
        config_path = loader._config_path
        
        # Read current config
        with open(config_path, 'r', encoding='utf-8') as f:
            import json
            config = json.load(f)
        
        # Update frontend_defaults
        config['frontend_defaults'] = {
            'model': data.get('model', ''),
            'streaming': data.get('streaming', True),
            'context_size': data.get('context_size', 15),
            'max_tokens': data.get('max_tokens', 13),
            'temperature': data.get('temperature', 0.1),
            'repeat_penalty': data.get('repeat_penalty', 1.2),
            'host': data.get('host', '127.0.0.1'),
            'port': data.get('port', 8080),
            'compute_mode': data.get('compute_mode', 'auto'),
            'gpu_layers': data.get('gpu_layers', 999),
            'threads': data.get('threads', 0),
            'advanced_settings_open': data.get('advanced_settings_open', False)
        }
        
        # Save config
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        return jsonify({'success': True, 'message': 'Configuration saved'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@llm_bp.route('/models', methods=['GET'])
def get_models():
    """Get list of available language models."""
    try:
        models = get_all_language_models()
        
        # Add existence check for each model
        loader = ConfigLoader()
        language_dir = loader.get_language_model_dir()
        
        for model in models:
            file_path = os.path.join(language_dir, model['file_name'])
            model['exists'] = os.path.exists(file_path)
        
        return jsonify(models), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@llm_bp.route('/models/refresh', methods=['GET'])
def refresh_models():
    """Refresh and return all models (language and voice)."""
    try:
        loader = ConfigLoader()
        config_data = loader._config
        
        language_models = config_data.get('language_models', [])
        voice_models = config_data.get('voice_models', [])
        
        # Check existence for language models
        language_dir = loader.get_language_model_dir()
        for model in language_models:
            file_path = os.path.join(language_dir, model['file_name'])
            model['exists'] = os.path.exists(file_path)
        
        # Check existence for voice models
        voice_dir = loader.get_voice_model_dir()
        for model in voice_models:
            file_path = os.path.join(voice_dir, model['file_name'])
            model['exists'] = os.path.exists(file_path)
        
        return jsonify({
            'language': language_models,
            'voice': voice_models
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@llm_bp.route('/config/directories', methods=['POST'])
def save_directories():
    """Save model directory paths."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        language_dir = data.get('language', '')
        voice_dir = data.get('voice', '')
        
        # Load current config
        loader = ConfigLoader()
        config_path = loader._config_path
        
        with open(config_path, 'r', encoding='utf-8') as f:
            import json
            config = json.load(f)
        
        # Update directories
        if 'model_directories' not in config:
            config['model_directories'] = {}
        
        if language_dir:
            config['model_directories']['language'] = language_dir
        if voice_dir:
            config['model_directories']['voice'] = voice_dir
        
        # Save config
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        return jsonify({'success': True, 'message': 'Directories saved'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@llm_bp.route('/models/manage', methods=['POST'])
def manage_models():
    """Add or remove models."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        action = data.get('action')
        model_type = data.get('type')
        model_data = data.get('data', {})
        
        manager = ConfigManager()
        
        if action == 'add':
            if model_type == 'language':
                success = manager.add_language_model(
                    file_name=model_data.get('file_name'),
                    nickname=model_data.get('nickname'),
                    parameters_billions=model_data.get('parameters_billions', 0),
                    check_exists=False
                )
                if success:
                    return jsonify({'success': True, 'message': 'Model added'}), 200
                else:
                    return jsonify({'error': 'Model already exists'}), 400
            else:
                # Voice models - add to config manually
                loader = ConfigLoader()
                config_path = loader._config_path
                
                with open(config_path, 'r', encoding='utf-8') as f:
                    import json
                    config = json.load(f)
                
                if 'voice_models' not in config:
                    config['voice_models'] = []
                
                # Check if already exists
                for model in config['voice_models']:
                    if model.get('file_name') == model_data.get('file_name'):
                        return jsonify({'error': 'Model already exists'}), 400
                
                config['voice_models'].append({
                    'file_name': model_data.get('file_name'),
                    'nickname': model_data.get('nickname')
                })
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                return jsonify({'success': True, 'message': 'Voice model added'}), 200
        
        elif action == 'remove':
            if model_type == 'language':
                success = manager.remove_language_model(model_data.get('file_name'))
                if success:
                    return jsonify({'success': True, 'message': 'Model removed'}), 200
                else:
                    return jsonify({'error': 'Model not found'}), 404
            else:
                # Voice models - remove manually
                loader = ConfigLoader()
                config_path = loader._config_path
                
                with open(config_path, 'r', encoding='utf-8') as f:
                    import json
                    config = json.load(f)
                
                original_count = len(config.get('voice_models', []))
                config['voice_models'] = [
                    m for m in config.get('voice_models', [])
                    if m.get('file_name') != model_data.get('file_name')
                ]
                
                if len(config['voice_models']) < original_count:
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)
                    return jsonify({'success': True, 'message': 'Voice model removed'}), 200
                else:
                    return jsonify({'error': 'Model not found'}), 404
        
        return jsonify({'error': 'Invalid action'}), 400
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@llm_bp.route('/server/start', methods=['POST'])
def start_server():
    """Start the LLM server."""
    global server_status, llm_instance
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No configuration provided'}), 400
        
        # Check if server is already running
        if server_status in ['starting', 'running']:
            return jsonify({'error': 'Server is already running or starting'}), 400
        
        server_status = 'starting'
        
        # Create args object for LocalLLM
        class ServerArgs:
            def __init__(self, config):
                loader = ConfigLoader()
                
                # Get model path
                self.model = loader.get_model_path(config.get('model', ''))
                
                # Server settings
                self.host = config.get('host', '127.0.0.1')
                self.port = config.get('port', 8080)
                
                # Model settings - convert slider values to actual values
                context_slider = config.get('context_size', 15)
                self.context_size = 2 ** int(context_slider)
                
                max_tokens_slider = config.get('max_tokens', 13)
                self.max_new_tokens = 2 ** int(max_tokens_slider)
                self.n_predict = self.max_new_tokens
                
                self.temperature = config.get('temperature', 0.1)
                self.repeat_penalty = config.get('repeat_penalty', 1.2)
                
                # Compute mode
                compute_mode = config.get('compute_mode', 'auto')
                self.cpu = compute_mode == 'cpu'
                self.gpu = compute_mode == 'gpu'
                
                # GPU/CPU specific settings
                self.gpu_layers = config.get('gpu_layers', 999)
                self.threads = config.get('threads', 0)
                
                # Server mode
                self.server_only = True
                self.inference_only = False
                self.inference_port = None
                
                # Additional settings
                self.stop = []
                self.logs = True
                self.timeout = 120.0
        
        try:
            args = ServerArgs(data)
        except Exception as e:
            server_status = 'error'
            return jsonify({'error': f'Invalid configuration: {str(e)}'}), 400
        
        # Start server in background thread
        import threading
        def run_server():
            global server_status, llm_instance
            try:
                llm_instance = LocalLMM(logger=logger, args=args)
                llm_instance.run()
                server_status = 'running'
            except Exception as e:
                logger.error(f"Server error: {e}")
                server_status = 'error'
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        return jsonify({'success': True, 'message': 'Server starting...'}), 200
        
    except Exception as e:
        server_status = 'error'
        return jsonify({'error': str(e)}), 500

@llm_bp.route('/server/stop', methods=['POST'])
def stop_server():
    """Stop the LLM server."""
    global server_status, llm_instance
    
    try:
        if server_status not in ['running', 'starting']:
            return jsonify({'error': 'Server is not running'}), 400
        
        server_status = 'stopping'
        
        # Shutdown the server
        if llm_instance:
            llm_instance.shutdown()
            llm_instance = None
        
        server_status = 'stopped'
        
        return jsonify({'success': True, 'message': 'Server stopped'}), 200
        
    except Exception as e:
        server_status = 'error'
        return jsonify({'error': str(e)}), 500

@llm_bp.route('/server/status', methods=['GET'])
def get_server_status():
    """Get current server status."""
    global server_status
    
    return jsonify({'status': server_status}), 200
