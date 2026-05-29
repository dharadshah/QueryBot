import gradio as gr
import requests
import uuid
import time

FASTAPI_URL = "http://localhost:8000/chat"
CUSTOMERS_URL = "http://localhost:8000/customers"


CSS = """
.gradio-container, .gradio-container * {
    color: #000000 !important;
    font-size: 20px !important;
}
.svelte-1ed2p3z, .message, .message p, .message span,
.message div, .prose, .prose p, .prose span {
    color: #000000 !important;
    font-size: 20px !important;
}
textarea, textarea * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    font-size: 20px !important;
}
[data-testid="bot"] * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    font-size: 20px !important;
}
[data-testid="user"] * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    font-size: 20px !important;
}

button, label, .label-wrap {
    font-size: 20px !important;
}
"""




def _load_customers_at_startup(max_attempts: int = 10) -> list:
    for attempt in range(max_attempts):
        try:
            response = requests.get(CUSTOMERS_URL, timeout=5)
            response.raise_for_status()
            data = response.json()
            result = [(c["name"], c["customer_id"]) for c in data]
            print(f"Customers loaded: {len(result)}")
            return result
        except Exception:
            time.sleep(1)
    print("Could not load customers after retries.")
    return []


# Load once at module level — runs when Gradio imports this file
CUSTOMER_LIST = _load_customers_at_startup()
CUSTOMER_CHOICES = [name for name, _ in CUSTOMER_LIST]
CUSTOMER_MAP = {name: cid for name, cid in CUSTOMER_LIST}


def chat(
    user_message: str,
    history: list,
    session_id: str,
    role: str,
    customer_name: str,
):
    if not user_message.strip():
        yield "", history, session_id
        return

    if not session_id:
        session_id = str(uuid.uuid4())

    history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": "..."},
    ]
    yield "", history, session_id

    payload = {
        "question": user_message,
        "session_id": session_id,
        "role": role.lower(),
    }

    if role.lower() == "customer" and customer_name:
        customer_id = CUSTOMER_MAP.get(customer_name)
        if customer_id:
            payload["customer_id"] = customer_id

    try:
        response = requests.post(FASTAPI_URL, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        answer = data.get("answer", "No answer returned.")
        history[-1] = {"role": "assistant", "content": answer}
        yield "", history, session_id

    except requests.exceptions.ConnectionError:
        history[-1] = {
            "role": "assistant",
            "content": "Cannot connect to the QueryBot API. Please make sure the server is running.",
        }
        yield "", history, session_id

    except requests.exceptions.Timeout:
        history[-1] = {
            "role": "assistant",
            "content": "The request timed out. Please try again.",
        }
        yield "", history, session_id

    except Exception:
        history[-1] = {
            "role": "assistant",
            "content": "An unexpected error occurred. Please try again.",
        }
        yield "", history, session_id


def clear_chat():
    return [], "", str(uuid.uuid4())


with gr.Blocks(css=CSS) as demo:

    session_state = gr.State("")

    with gr.Column():
        gr.HTML(
            "<h1 style='text-align:center; color:#0f3460; margin-bottom:4px;'>QueryBot</h1>"
        )
        gr.HTML(
            "<p style='text-align:center; color:#333333; font-size:15px; margin-bottom:16px;'>"
            "Ask questions about your eCommerce data in plain English."
            "</p>"
        )

        with gr.Row():
            role_selector = gr.Dropdown(
                choices=["Guest", "Customer", "Admin"],
                value="Guest",
                label="Access Role",
                scale=1,
            )
            customer_selector = gr.Dropdown(
                choices=CUSTOMER_CHOICES,
                label="Select Customer",
                value=CUSTOMER_CHOICES[0] if CUSTOMER_CHOICES else None,
                visible=False,
                scale=2,
            )

        chatbot = gr.Chatbot(
            label="",
            height=460,
            show_label=False,
            render_markdown=True,
            layout="bubble",
        )

        with gr.Row():
            question_input = gr.Textbox(
                placeholder="Ask a question about your data...",
                show_label=False,
                scale=8,
                container=False,
                autofocus=True,
            )
            submit_btn = gr.Button(
                "Ask",
                variant="primary",
                scale=1,
                min_width=80,
            )

        with gr.Row():
            clear_btn = gr.Button(
                "Clear Chat",
                variant="secondary",
                size="sm",
            )

        gr.HTML(
            "<div style='text-align:center; margin-top:10px; color:#555555; font-size:13px;'>"
            "Results are limited to 20 rows per query. "
            "Only SELECT queries are permitted."
            "</div>"
        )

        gr.Examples(
            examples=[
                ["How many products are in the electronics category?"],
                ["What are the total sales per customer?"],
                ["List all pending orders with customer names"],
                ["Which products have the highest unit price?"],
                ["How many orders were delivered?"],
            ],
            inputs=question_input,
            label="Example Questions",
        )

    # Show/hide customer selector based on role — pure UI, no I/O
    role_selector.change(
        fn=lambda role: gr.update(visible=role.lower() == "customer"),
        inputs=[role_selector],
        outputs=[customer_selector],
    )

    submit_btn.click(
        fn=chat,
        inputs=[question_input, chatbot, session_state, role_selector, customer_selector],
        outputs=[question_input, chatbot, session_state],
    )

    question_input.submit(
        fn=chat,
        inputs=[question_input, chatbot, session_state, role_selector, customer_selector],
        outputs=[question_input, chatbot, session_state],
    )

    clear_btn.click(
        fn=clear_chat,
        outputs=[chatbot, question_input, session_state],
    )


def launch():
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        quiet=True,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    launch()