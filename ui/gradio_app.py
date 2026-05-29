import gradio as gr
import requests
import uuid

FASTAPI_URL = "http://localhost:8000/chat"


def chat(user_message: str, history: list, session_id: str):
    if not user_message.strip():
        yield "", history, session_id
        return

    # Generate session ID on first message
    if not session_id:
        session_id = str(uuid.uuid4())

    # Show user message immediately while waiting for response
    history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": "..."},
    ]
    yield "", history, session_id

    try:
        response = requests.post(
            FASTAPI_URL,
            json={
                "question": user_message,
                "session_id": session_id,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        answer = data.get("answer", "No answer returned.")
        success = data.get("success", False)
        error = data.get("error", None)

        display = answer

        # Replace the placeholder with the real answer
        history[-1] = {"role": "assistant", "content": display}
        yield "", history, session_id

    except requests.exceptions.ConnectionError:
        history[-1] = {
            "role": "assistant",
            "content": (
                "Cannot connect to the QueryBot API. "
                "Please make sure the FastAPI server is running on port 8000."
            ),
        }
        yield "", history, session_id

    except requests.exceptions.Timeout:
        history[-1] = {
            "role": "assistant",
            "content": "The request timed out. Please try again.",
        }
        yield "", history, session_id

    except Exception as e:
        history[-1] = {
            "role": "assistant",
            "content": f"An unexpected error occurred: {str(e)}",
        }
        yield "", history, session_id


def clear_chat() -> tuple[list, str, str]:
    return [], "", str(uuid.uuid4())


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



/* Buttons and labels */
button, label, .label-wrap {
    font-size: 20px !important;
}
"""

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

        chatbot = gr.Chatbot(
            label="",
            height=500,
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

    submit_btn.click(
        fn=chat,
        inputs=[question_input, chatbot, session_state],
        outputs=[question_input, chatbot, session_state],
    )

    question_input.submit(
        fn=chat,
        inputs=[question_input, chatbot, session_state],
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