from __future__ import unicode_literals
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn
import signal

from ydl_server.db import JobsDB

from ydl_server.ydlhandler import YdlHandler
from ydl_server.jobshandler import JobsHandler
from ydl_server.config import app_config

from ydl_server.routes import routes

if __name__ == "__main__":
    JobsDB.init()

    middleware = [Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])]

    app = Starlette(
        routes=routes,
        debug=app_config["ydl_server"].get("debug", False),
        middleware=middleware,
    )

    app.state.running = True
    app.state.jobshandler = JobsHandler(app_config)
    app.state.ydlhandler = YdlHandler(app_config, app.state.jobshandler)

    def shutdown():
        if not app.state.running:
            return
        print("Shutting down...")
        app.state.jobshandler.finish()
        app.state.ydlhandler.finish()
        print("Waiting for workers to wrap up...")
        app.state.ydlhandler.join()
        app.state.jobshandler.join()
        print("Shutdown complete.")
        app.state.running = False

    signal.signal(signal.SIGINT, lambda sig, frame: shutdown())
    signal.signal(signal.SIGTERM, lambda sig, frame: shutdown())

    app.state.ydlhandler.start()
    print("Started download threads")
    app.state.jobshandler.start(app.state.ydlhandler.queue)
    print("Started jobs manager thread")

    app.state.ydlhandler.resume_pending()

    uvicorn.run(
        app,
        host=app_config["ydl_server"].get("host"),
        port=app_config["ydl_server"].get("port"),
        log_level=("debug" if app_config["ydl_server"].get("debug", False) else "info"),
        forwarded_allow_ips=app_config["ydl_server"].get("forwarded_allow_ips", None),
        proxy_headers=app_config["ydl_server"].get("proxy_headers", True),
    )
    shutdown()
