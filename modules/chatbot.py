"""
Chatbot module for the refactored DSD project.

This module defines a simple ``Chatbot`` class that couples conversation
history with knowledge graph retrieval to generate responses.  It is
intentionally lightweight and self‑contained, avoiding external large
language model (LLM) dependencies in favour of a deterministic stubbed
response.  The purpose of this module is to demonstrate an architecture
similar to the original project while operating independently of the
underlying environment.

The ``Chatbot`` maintains histories keyed by a conversation ID.  When a
question is processed, the chatbot searches its knowledge graph for
relevant information using ``Neo4jGraph.query_graph``.  The returned
facts are combined with the user's question and a trivial generation
heuristic to produce a response.  Conversation history is updated with
both the user question and the chatbot reply.  This design allows the
chatbot to maintain context across multiple turns and to clear the
context when needed.

Note:
    This implementation intentionally avoids connecting to an actual
    Neo4j database or invoking a remote LLM.  Instead, the graph
    retrieval is simulated via a simple in‑memory data store.  Should
    users wish to integrate a real database or model, the
    ``Neo4jGraph`` and ``generate_response`` methods can be extended
    accordingly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
import os
from typing import Dict, List, Any, Optional

# Attempt to import the OpenAI SDK.  If it's unavailable the chatbot will
# gracefully fall back to a deterministic response generator.
try:  # pragma: no cover - import guarded for environments without openai
    import openai  # type: ignore
except Exception:  # pragma: no cover
    openai = None  # type: ignore

from modules.neo4j_skoda_graph import Neo4jGraph


@dataclass
class Chatbot:
    """A chatbot that can optionally leverage OpenAI for generative responses.

    The chatbot maintains a per‑conversation history and consults a
    lightweight Neo4j knowledge graph stub to enrich responses.  When
    OpenAI's SDK is available and an API key is configured via the
    ``OPENAI_API_KEY`` environment variable, the chatbot will use the
    ChatCompletion API to generate replies.  Otherwise, it falls back
    to a deterministic response that echoes the user's question and
    includes any retrieved facts.
    """

    graph: Neo4jGraph = field(default_factory=Neo4jGraph)
    histories: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    openai_model: str = field(default="gpt-3.5-turbo")
    system_prompt: Optional[str] = field(default=None)

    def process_chat_request(self, question: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Process a user question and return a response.

        A new conversation ID will be generated if none is provided.  The
        method appends the user's message to history, queries the
        knowledge graph for relevant facts, and delegates response
        generation to OpenAI if available.  The assistant's reply is
        subsequently appended to the conversation history.

        Parameters
        ----------
        question:
            The user's natural language input.
        conversation_id:
            An optional identifier for the ongoing conversation.  If ``None``
            is supplied, a new conversation will be started.

        Returns
        -------
        dict
            A dictionary containing the ``conversation_id`` used and the
            chatbot's ``response``.
        """
        # Initialise the conversation history if necessary.
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
            self.histories[conversation_id] = []
        if conversation_id not in self.histories:
            self.histories[conversation_id] = []

        # Record the user's message.
        self.histories[conversation_id].append({"role": "user", "content": question})

        # Query the knowledge graph.
        facts = self.graph.query_graph(question)

        # Determine response via OpenAI or fallback.
        response = self._generate_via_openai(question, facts, conversation_id)

        # Record the assistant's reply.
        self.histories[conversation_id].append({"role": "assistant", "content": response})

        return {"conversation_id": conversation_id, "response": response}

    def _generate_via_openai(self, question: str, facts: List[str], conversation_id: str) -> str:
        """Attempt to generate a response using OpenAI; fallback to deterministic.

        Parameters
        ----------
        question:
            The user's question.
        facts:
            Facts retrieved from the knowledge graph.
        conversation_id:
            The identifier of the current conversation whose history should
            be provided to the model.

        Returns
        -------
        str
            The generated response.
        """
        # If OpenAI SDK is unavailable or no API key is configured, fallback.
        api_key = os.getenv("OPENAI_API_KEY")
        if openai is None or not api_key:
            return self._generate_stub_response(question, facts)

        try:
            # Configure the API key lazily.  Doing this here avoids setting
            # global state when the module is imported in environments
            # lacking openai.
            openai.api_key = api_key  # type: ignore

            # Compose a system prompt incorporating any retrieved facts.
            system_content = self.system_prompt or "You are a knowledgeable assistant."
            if facts:
                facts_text = "; ".join(facts)
                system_content += f" Use the following facts when relevant: {facts_text}."

            messages: List[Dict[str, str]] = []
            messages.append({"role": "system", "content": system_content})
            # Append conversation history for context.
            for msg in self.histories.get(conversation_id, []):
                messages.append(msg)

            # Finally append the current user question (since history contains it too).
            # Duplicate user message at end is okay; OpenAI will consider it as the latest turn.
            messages.append({"role": "user", "content": question})

            # Call the ChatCompletion API.
            completion = openai.ChatCompletion.create(  # type: ignore
                model=self.openai_model,
                messages=messages,
                temperature=0.7,
            )
            return completion.choices[0].message.content.strip()  # type: ignore
        except Exception:
            # On error, fallback to deterministic response.
            return self._generate_stub_response(question, facts)

    def _generate_stub_response(self, question: str, facts: List[str]) -> str:
        """Fallback deterministic response generator used when OpenAI is unavailable."""
        if facts:
            facts_text = "; ".join(facts)
            return (
                f"You asked: '{question}'. I found the following information: {facts_text}."
            )
        return f"You asked: '{question}', but I couldn't find any relevant information."

    def clear_conversation_history(self, conversation_id: str) -> bool:
        """Clear the stored messages for a given conversation.

        Parameters
        ----------
        conversation_id:
            The identifier of the conversation to clear.

        Returns
        -------
        bool
            ``True`` if the conversation existed and was cleared, ``False`` otherwise.
        """
        if conversation_id in self.histories:
            del self.histories[conversation_id]
            return True
        return False
