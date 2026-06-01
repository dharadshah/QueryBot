import threading
import time
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
    # Wait for FastAPI to be fully ready
    time.sleep(5)

    # Load customers BEFORE launching Gradio
    # so CUSTOMER_LIST is populated before the UI renders
    from ui.gradio_app import _load_customers_at_startup
    import ui.gradio_app as gradio_module
    gradio_module.CUSTOMER_LIST = _load_customers_at_startup()
    gradio_module.CUSTOMER_CHOICES = [name for name, _ in gradio_module.CUSTOMER_LIST]
    gradio_module.CUSTOMER_MAP = {name: cid for name, cid in gradio_module.CUSTOMER_LIST}

    from ui.gradio_app import launch
    launch()


if __name__ == "__main__":
    setup_logging(log_level=settings.log_level)

    fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
    gradio_thread = threading.Thread(target=start_gradio, daemon=True)

    fastapi_thread.start()
    gradio_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down QueryBot.")