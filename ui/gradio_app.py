import gradio as gr
import requests
import json

FASTAPI_URL = "http://localhost:8000/chat"


def chat(user_message: str, history: list) -> tuple[str, list]:
    if not user_message.strip():
        return "", history

    try:
        response = requests.post(
            FASTAPI_URL,
            json={"question": user_message},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()

        answer = data.get("answer", "No answer returned.")
        sql = data.get("sql_generated", "")
        rows = data.get("rows_returned", 0)
        success = data.get("success", False)
        error = data.get("error", None)

        # Build the display message
        display = answer

        if sql:
            display += f"\n\n**SQL Generated:**\n```sql\n{sql}\n```"

        if rows is not None and success:
            display += f"\n\n*Rows returned: {rows}*"

        if not success and error:
            display += f"\n\n*Error: {error}*"

        history.append((user_message, display))
        return "", history

    except requests.exceptions.ConnectionError:
        error_msg = (
            "Cannot connect to the QueryBot API. "
            "Please make sure the FastAPI server is running on port 8000."
        )
        history.append((user_message, error_msg))
        return "", history

    except requests.exceptions.Timeout:
        error_msg = "The request timed out. Please try again."
        history.append((user_message, error_msg))
        return "", history

    except Exception as e:
        error_msg = f"An unexpected error occurred: {str(e)}"
        history.append((user_message, error_msg))
        return "", history


def clear_chat() -> tuple[list, str]:
    return [], ""


with gr.Blocks(
    title="QueryBot",
    theme=gr.themes.Soft(),
    css="""
        .container { max-width: 900px; margin: auto; }
        .header { text-align: center; padding: 20px 0 10px 0; }
        .header h1 { font-size: 2rem; font-weight: 700; color: #0f3460; }
        .header p { color: #555555; font-size: 1rem; margin-top: 4px; }
        .chatbot { border-radius: 8px; }
        footer { display: none; }
    """,
) as demo:

    with gr.Column(elem_classes="container"):

        with gr.Column(elem_classes="header"):
            gr.HTML("<h1>QueryBot</h1>")
            gr.HTML(
                "<p>Ask questions about your eCommerce data in plain English.</p>"
            )

        chatbot = gr.Chatbot(
            label="",
            height=480,
            elem_classes="chatbot",
            bubble_full_width=False,
            show_label=False,
            render_markdown=True,
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
            """
            <div style='text-align:center; margin-top:12px; color:#888; font-size:0.85rem;'>
                Results are limited to 20 rows per query.
                Only SELECT queries are permitted.
            </div>
            """
        )

        # Example questions
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

    # Wire up interactions
    submit_btn.click(
        fn=chat,
        inputs=[question_input, chatbot],
        outputs=[question_input, chatbot],
    )

    question_input.submit(
        fn=chat,
        inputs=[question_input, chatbot],
        outputs=[question_input, chatbot],
    )

    clear_btn.click(
        fn=clear_chat,
        outputs=[chatbot, question_input],
    )


def launch():
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_api=False,
        quiet=True,
    )


if __name__ == "__main__":
    launch()