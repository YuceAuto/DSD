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
from typing import Dict, List, Any

from modules.skoda.graph.neo4j_skoda_graph import Neo4jGraph


@dataclass
class Chatbot:
    """A simple chatbot that integrates conversation history and a knowledge graph."""

    graph: Neo4jGraph = field(default_factory=Neo4jGraph)
    histories: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)

    def process_chat_request(self, question: str, conversation_id: str | None = None) -> Dict[str, Any]:
        """Process a user question and return a response.

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
        # Normalise the conversation identifier and initialise history if needed.
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
            self.histories[conversation_id] = []
        if conversation_id not in self.histories:
            # Start a new history if the provided ID was unknown.
            self.histories[conversation_id] = []

        # Append the user's message to the history.
        self.histories[conversation_id].append({"role": "user", "content": question})

        # Retrieve relevant information from the knowledge graph.
        facts = self.graph.query_graph(question)

        # Generate a response based on the question and retrieved facts.
        response = self._generate_response(question, facts)

        # Append the assistant's reply to the history.
        self.histories[conversation_id].append({"role": "assistant", "content": response})

        return {"conversation_id": conversation_id, "response": response}

    def _generate_response(self, question: str, facts: List[str]) -> str:
        """Generate a response from the question and retrieved facts.

        In lieu of a full LLM, this method composes a deterministic response
        that echoes the user's question and includes relevant facts from the
        knowledge graph.  If no facts are found, it informs the user that
        nothing relevant was discovered.

        Parameters
        ----------
        question:
            The user's input.
        facts:
            A list of strings representing information retrieved from the
            knowledge graph.

        Returns
        -------
        str
            A chat response.
        """
        if facts:
            facts_text = "; ".join(facts)
            return f"You asked: '{question}'. I found the following information: {facts_text}."
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
