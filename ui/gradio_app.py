import gradio as gr
import requests
import uuid

FASTAPI_URL = "http://localhost:8000/chat"


def chat(user_message: str, history: list, session_id: str) -> tuple[str, list, str]:
    if not user_message.strip():
        return "", history, session_id

    # Generate session ID on first message
    if not session_id:
        session_id = str(uuid.uuid4())

    try:
        response = requests.post(
            FASTAPI_URL,
            json={
                "question": user_message,
                "session_id": session_id,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()

        answer = data.get("answer", "No answer returned.")
        success = data.get("success", False)
        error = data.get("error", None)

        display = answer

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": display})
        return "", history, session_id

    except requests.exceptions.ConnectionError:
        error_msg = (
            "Cannot connect to the QueryBot API. "
            "Please make sure the FastAPI server is running on port 8000."
        )
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": error_msg})
        return "", history, session_id

    except requests.exceptions.Timeout:
        error_msg = "The request timed out. Please try again."
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": error_msg})
        return "", history, session_id

    except Exception as e:
        error_msg = f"An unexpected error occurred: {str(e)}"
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": error_msg})
        return "", history, session_id


def clear_chat() -> tuple[list, str, str]:
    # Generate a new session ID when chat is cleared
    return [], "", str(uuid.uuid4())


with gr.Blocks() as demo:

    # session_id stored as hidden state — persists across messages
    session_state = gr.State("")

    with gr.Column():
        gr.HTML("<h1 style='text-align:center; color:#0f3460;'>QueryBot</h1>")
        gr.HTML(
            "<p style='text-align:center; color:#555;'>"
            "Ask questions about your eCommerce data in plain English."
            "</p>"
        )

        chatbot = gr.Chatbot(
            label="",
            height=480,
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
            "<div style='text-align:center; margin-top:12px; color:#888; font-size:0.85rem;'>"
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