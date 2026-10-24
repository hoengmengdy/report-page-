"""Local entry point and WSGI application."""
import os
from backend import create_app

app = create_app()

if __name__ == "__main__":
    from werkzeug.serving import WSGIRequestHandler

    class SafeRequestHandler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            self.log("info", "%s %s %s", self.command, self.path.split("?")[0], code)

    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")),
            debug=False, request_handler=SafeRequestHandler)
