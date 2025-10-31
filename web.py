from flask import Flask, send_from_directory, abort
import os
import config

app = Flask(__name__)

@app.route('/ava/<filename>')
def serve_avatar(filename):
    """Serve avatar files"""
    try:
        return send_from_directory(config.MEDIA_AVA_PATH, filename)
    except FileNotFoundError:
        abort(404)

@app.route('/media/<filename>')
def serve_media(filename):
    """Serve media files"""
    try:
        return send_from_directory(config.MEDIA_FILES_PATH, filename)
    except FileNotFoundError:
        abort(404)

@app.route('/health')
def health():
    """Health check endpoint"""
    return {"status": "ok", "message": "Server is running"}

def run_web_server():
    """Run Flask web server"""
    # For HTTPS, you need SSL certificate
    # If you don't have SSL cert, use HTTP instead
    
    # Without SSL (use http://)
    app.run(host='0.0.0.0', port=config.PORT, debug=False)
    
    # With SSL (use https://) - uncomment and add your cert files
    # app.run(
    #     host='0.0.0.0',
    #     port=config.PORT,
    #     debug=False,
    #     ssl_context=('cert.pem', 'key.pem')
    # )

if __name__ == '__main__':
    run_web_server()
