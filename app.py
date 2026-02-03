"""
Main FastAPI application for the refactored DSD project.

This module exposes a simple REST API that allows clients to interact with a
chatbot powered by a lightweight knowledge graph and conversation memory.  The
chatbot is implemented in ``modules.chat.chatbot.Chatbot`` and uses an in‑
memory store for conversation context along with a rudimentary Neo4j graph
abstraction for domain knowledge.  The API defines two endpoints:

* ``POST /chat`` – accepts a user query and optional conversation identifier
  and returns a chatbot response along with a conversation identifier.  The
  conversation identifier can be reused in subsequent requests to maintain
  context.
* ``POST /clear`` – accepts a conversation identifier and purges any stored
  history for that conversation.

By default the chatbot will rely on a deterministic rule‑based response
generator.  If the ``OPENAI_API_KEY`` environment variable is set and the
OpenAI Python SDK is installed, the chatbot will instead call OpenAI's
ChatCompletion API to produce generative responses.  This simplified
application demonstrates how to orchestrate request/response cycles while
remaining easy to understand.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from modules.chat.chatbot import Chatbot


class ChatRequest(BaseModel):
    """Request body model for the chat endpoint."""

    question: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    """Response model returned by the chat endpoint."""

    conversation_id: str
    response: str


class ClearRequest(BaseModel):
    """Request body model for clearing a conversation."""

    conversation_id: str


class ClearResponse(BaseModel):
    """Response model confirming a cleared conversation."""

    conversation_id: str
    cleared: bool


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns
    -------
    FastAPI
        A configured FastAPI instance with registered routes.
    """
    app = FastAPI(title="DSD Chatbot API", version="1.0.0")
    chatbot = Chatbot()

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        """Handle a chat request by delegating to the Chatbot instance.

        Parameters
        ----------
        request:
            The incoming request containing a user question and optional
            conversation identifier.  If no identifier is provided, a new
            conversation will be started automatically.

        Returns
        -------
        ChatResponse
            The generated response and the conversation identifier to use for
            subsequent messages.
        """
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="Question must not be empty.")
        result = chatbot.process_chat_request(
            question=request.question, conversation_id=request.conversation_id
        )
        return ChatResponse(
            conversation_id=result["conversation_id"], response=result["response"]
        )

    @app.post("/clear", response_model=ClearResponse)
    async def clear_history(request: ClearRequest) -> ClearResponse:
        """Clear the conversation history for the provided identifier.

        Parameters
        ----------
        request:
            The incoming request specifying which conversation to clear.

        Returns
        -------
        ClearResponse
            Confirms that the conversation history has been removed.  If the
            conversation does not exist, a 404 error is raised.
        """
        cleared = chatbot.clear_conversation_history(request.conversation_id)
        if not cleared:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return ClearResponse(conversation_id=request.conversation_id, cleared=True)

    return app


app = create_app()
