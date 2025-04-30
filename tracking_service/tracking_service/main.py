"""Main entry point for the tracking service."""

import uvicorn

from tracking_service.server import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
