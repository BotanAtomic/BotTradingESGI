from http.server import HTTPServer, BaseHTTPRequestHandler


def create_handler(logger):

    class LogHandler(BaseHTTPRequestHandler):

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = "<html><body>"
            for log in logger.logs:
                html += F"<p>{log}</p>"
            html += "<html><body>"

            self.wfile.write(html.encode())

        def log_message(self, _, *args):
            return

    return LogHandler


class HttpServer:

    def __init__(self, logger):
        self.logger = logger
        self.http_server = HTTPServer(('0.0.0.0', 80), create_handler(logger))

    def start(self):
        self.logger.init_log("starting http server...")
        self.http_server.serve_forever()
