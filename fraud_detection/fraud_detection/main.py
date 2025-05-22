"""Main entry point for the Fraud Detection Service."""

import uvicorn

from fraud_detection.server import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
