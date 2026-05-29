import threading
import time
import os
import uvicorn
from app.main import app
from app.observability.logger import setup_logging
from app.config import settings


def start_fastapi():
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower(),
    )


def start_gradio():
    time.sleep(5)
    from ui.gradio_app import launch
    launch()


def init_docker_db():
    if os.environ.get("RUNNING_IN_DOCKER"):
        print("Docker environment detected — initialising database...")
        from docker.init_db import wait_for_db, create_database
        conn = wait_for_db()
        create_database(conn)
        conn.close()
        from seed.seed_data import run
        run()


if __name__ == "__main__":
    setup_logging(log_level=settings.log_level)

    init_docker_db()

    fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
    gradio_thread = threading.Thread(target=start_gradio, daemon=True)

    fastapi_thread.start()
    gradio_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down QueryBot.")