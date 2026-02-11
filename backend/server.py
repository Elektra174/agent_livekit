from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from livekit import api
import os
import logging
from dotenv import load_dotenv
from datetime import datetime
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Enable CORS for all origins
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Frontend directory path (relative to backend directory)
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

# In-memory settings storage (in production, use a database)
user_settings = {}


@app.route('/')
def index():
    """Serve the main frontend index.html"""
    logger.info(f"Serving index.html from FRONTEND_DIR: {FRONTEND_DIR}")
    logger.info(f"FRONTEND_DIR exists: {os.path.exists(FRONTEND_DIR)}")
    logger.info(f"index.html exists: {os.path.exists(os.path.join(FRONTEND_DIR, 'index.html'))}")
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/voice-settings')
def voice_settings():
    """Serve the voice settings page"""
    logger.info(f"Serving voice-settings.html from FRONTEND_DIR: {FRONTEND_DIR}")
    logger.info(f"voice-settings.html exists: {os.path.exists(os.path.join(FRONTEND_DIR, 'voice-settings.html'))}")
    return send_from_directory(FRONTEND_DIR, 'voice-settings.html')





@app.route('/app.js')
def serve_app_js():
    """Serve the frontend app.js"""
    return send_from_directory(FRONTEND_DIR, 'app.js', mimetype='application/javascript')


@app.route('/style.css')
def serve_style_css():
    """Serve the frontend style.css"""
    return send_from_directory(FRONTEND_DIR, 'style.css', mimetype='text/css')


@app.route('/manifest.json')
def serve_manifest_json():
    """Serve the frontend manifest.json"""
    return send_from_directory(FRONTEND_DIR, 'manifest.json', mimetype='application/json')


@app.route('/livekit-client.umd.js')
def serve_livekit_client():
    """Serve the LiveKit client library"""
    return send_from_directory(FRONTEND_DIR, 'livekit-client.umd.js', mimetype='application/javascript')




# LiveKit configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Validate required environment variables
if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
    logger.error("Missing required LiveKit environment variables")
    raise ValueError("LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set")

logger.info(f"LiveKit URL: {LIVEKIT_URL}")
logger.info("Flask token server initialized")


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'omni-agent-token-server'
    })


@app.route('/api/settings', methods=['POST'])
def save_settings():
    """Save user settings"""
    try:
        if not request.is_json:
            logger.warning("Invalid content type for /api/settings endpoint")
            return jsonify({
                'error': 'Content-Type must be application/json'
            }), 400

        data = request.json

        if not data:
            logger.warning("Empty request body for /api/settings endpoint")
            return jsonify({
                'error': 'Request body cannot be empty'
            }), 400

        # Extract settings from request
        participant_name = data.get('participant_name', 'default')
        settings = {
            'selected_voice_api': data.get('selected_voice_api', 'aoede'),
            'target_lang': data.get('target_lang', 'English'),
            'teacher_mode': data.get('teacher_mode', False),
            'speech_speed': data.get('speech_speed', 1.1)
        }

        # Store settings for the participant
        user_settings[participant_name] = settings

        logger.info(f"Settings saved for participant '{participant_name}': {settings}")

        return jsonify({
            'message': 'Settings saved successfully',
            'settings': settings
        }), 200

    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error while saving settings'
        }), 500


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Retrieve user settings"""
    try:
        participant_name = request.args.get('participant_name', 'default')

        if participant_name in user_settings:
            settings = user_settings[participant_name]
            logger.info(f"Settings retrieved for participant '{participant_name}': {settings}")
            return jsonify({
                'settings': settings
            }), 200
        else:
            # Return default settings if none exist
            default_settings = {
                'selected_voice_api': 'aoede',
                'target_lang': 'English',
                'teacher_mode': False,
                'speech_speed': 1.1
            }
            logger.info(f"No settings found for participant '{participant_name}', returning defaults")
            return jsonify({
                'settings': default_settings
            }), 200

    except Exception as e:
        logger.error(f"Error retrieving settings: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error while retrieving settings'
        }), 500


@app.route('/token', methods=['POST'])
def get_token():
    """Generate LiveKit access token for room participation"""
    try:
        # Validate request content type
        if not request.is_json:
            logger.warning("Invalid content type for /token endpoint")
            return jsonify({
                'error': 'Content-Type must be application/json'
            }), 400

        data = request.json

        # Validate required fields
        if not data:
            logger.warning("Empty request body for /token endpoint")
            return jsonify({
                'error': 'Request body cannot be empty'
            }), 400

        room_name = data.get('room_name', 'room-test-1')
        participant_name = data.get('participant_name')
        metadata = data.get('metadata')

        if not room_name:
            logger.warning("Missing room_name in request")
            return jsonify({
                'error': 'room_name is required'
            }), 400

        if not participant_name:
            logger.warning("Missing participant_name in request")
            return jsonify({
                'error': 'participant_name is required'
            }), 400

        logger.info(f"Generating token for participant '{participant_name}' in room '{room_name}'")

        # Parse metadata if provided
        settings = {}
        if metadata:
            try:
                settings = json.loads(metadata)
                logger.info(f"Settings from metadata: {settings}")
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in metadata, using empty settings")

        # Store settings for the participant
        user_settings[participant_name] = settings

        # Create access token with proper grants and metadata
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
            .with_identity(participant_name) \
            .with_name(participant_name) \
            .with_metadata(metadata or '') \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                agent=True, # Добавь это, чтобы комната знала об агентах
            ))

        logger.info(f"Token generated successfully for participant '{participant_name}' with metadata")

        return jsonify({
            'token': token.to_jwt(),
            'url': LIVEKIT_URL,
            'room_name': room_name,
            'participant_name': participant_name,
            'settings': settings
        }), 200

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({
            'error': f'Validation error: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"Error generating token: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error while generating token'
        }), 500


# start_agent removed as requested. We use automatic dispatch now.


@app.route('/rooms', methods=['GET'])
def list_rooms():
    """List all active rooms"""
    try:
        logger.info("Listing rooms")
        
        # Create a room service client
        room_service = api.RoomServiceClient(
            LIVEKIT_URL,
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET
        )
        
        # List rooms
        rooms = room_service.list_rooms()
        
        room_list = []
        for room in rooms:
            room_list.append({
                'sid': room.sid,
                'name': room.name,
                'num_participants': room.num_participants,
                'max_participants': room.max_participants,
                'creation_time': room.creation_time,
                'empty_timeout': room.empty_timeout
            })
        
        logger.info(f"Found {len(room_list)} active rooms")
        
        return jsonify({
            'rooms': room_list,
            'count': len(room_list)
        }), 200

    except Exception as e:
        logger.error(f"Error listing rooms: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error while listing rooms'
        }), 500


@app.route('/rooms', methods=['POST'])
def create_room():
    """Create a new room"""
    try:
        if not request.is_json:
            logger.warning("Invalid content type for /rooms POST endpoint")
            return jsonify({
                'error': 'Content-Type must be application/json'
            }), 400

        data = request.json
        room_name = data.get('room_name')

        if not room_name:
            logger.warning("Missing room_name in create room request")
            return jsonify({
                'error': 'room_name is required'
            }), 400

        # Optional parameters
        empty_timeout = data.get('empty_timeout', 300)  # 5 minutes default
        max_participants = data.get('max_participants', 0)  # 0 = unlimited

        logger.info(f"Creating room '{room_name}'")

        # Create a room service client
        room_service = api.RoomServiceClient(
            LIVEKIT_URL,
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET
        )
        
        # Create room
        room = room_service.create_room(
            api.CreateRoomRequest(
                name=room_name,
                empty_timeout=empty_timeout,
                max_participants=max_participants
            )
        )
        
        logger.info(f"Room '{room_name}' created successfully")

        return jsonify({
            'sid': room.sid,
            'name': room.name,
            'empty_timeout': room.empty_timeout,
            'max_participants': room.max_participants,
            'creation_time': room.creation_time
        }), 201

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({
            'error': f'Validation error: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"Error creating room: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error while creating room'
        }), 500


@app.route('/rooms/<room_name>', methods=['DELETE'])
def delete_room(room_name):
    """Delete a room"""
    try:
        logger.info(f"Deleting room '{room_name}'")

        # Create a room service client
        room_service = api.RoomServiceClient(
            LIVEKIT_URL,
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET
        )
        
        # Delete room
        room_service.delete_room(api.DeleteRoomRequest(room=room_name))
        
        logger.info(f"Room '{room_name}' deleted successfully")

        return jsonify({
            'message': f'Room {room_name} deleted successfully'
        }), 200

    except Exception as e:
        logger.error(f"Error deleting room: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error while deleting room'
        }), 500


@app.route('/rooms/<room_name>/participants', methods=['GET'])
def list_participants(room_name):
    """List all participants in a room"""
    try:
        logger.info(f"Listing participants for room '{room_name}'")

        # Create a room service client
        room_service = api.RoomServiceClient(
            LIVEKIT_URL,
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET
        )
        
        # List participants
        participants = room_service.list_participants(room_name)
        
        participant_list = []
        for participant in participants:
            participant_list.append({
                'sid': participant.sid,
                'identity': participant.identity,
                'name': participant.name,
                'state': participant.state,
                'tracks': len(participant.tracks),
                'metadata': participant.metadata,
                'joined_at': participant.joined_at
            })
        
        logger.info(f"Found {len(participant_list)} participants in room '{room_name}'")

        return jsonify({
            'room_name': room_name,
            'participants': participant_list,
            'count': len(participant_list)
        }), 200

    except Exception as e:
        logger.error(f"Error listing participants: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error while listing participants'
        }), 500


@app.route('/rooms/<room_name>/participants/<participant_identity>', methods=['DELETE'])
def remove_participant(room_name, participant_identity):
    """Remove a participant from a room"""
    try:
        logger.info(f"Removing participant '{participant_identity}' from room '{room_name}'")

        # Create a room service client
        room_service = api.RoomServiceClient(
            LIVEKIT_URL,
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET
        )
        
        # Remove participant
        room_service.remove_participant(
            api.RoomParticipantIdentity(
                room=room_name,
                identity=participant_identity
            )
        )
        
        logger.info(f"Participant '{participant_identity}' removed from room '{room_name}'")

        return jsonify({
            'message': f'Participant {participant_identity} removed from room {room_name}'
        }), 200

    except Exception as e:
        logger.error(f"Error removing participant: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error while removing participant'
        }), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    logger.warning(f"404 error: {request.path}")
    return jsonify({
        'error': 'Endpoint not found'
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    logger.warning(f"405 error: {request.method} {request.path}")
    return jsonify({
        'error': 'Method not allowed'
    }), 405


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"500 error: {str(error)}", exc_info=True)
    return jsonify({
        'error': 'Internal server error'
    }), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Starting Flask server on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
