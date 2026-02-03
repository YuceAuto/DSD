"""
Unit tests for the simplified Neo4jGraph and Chatbot classes.

These tests verify that the mock graph and chatbot behave as expected:

* The graph returns appropriate facts when keywords are present in the
  user's question.
* The chatbot maintains conversation history across multiple calls.
* Clearing a conversation removes its history and returns the correct
  boolean flag.

Run this test module with ``python -m unittest modules.test.neo4j_test``.
"""

import unittest

from modules.skoda.graph.neo4j_skoda_graph import Neo4jGraph
from modules.chat.chatbot import Chatbot


class TestNeo4jGraph(unittest.TestCase):
    """Test cases for the Neo4jGraph stub."""

    def setUp(self) -> None:
        self.graph = Neo4jGraph()

    def test_query_known_keyword(self) -> None:
        """Graph should return facts for a known keyword."""
        facts = self.graph.query_graph("Tell me about the battery and motor.")
        self.assertTrue(any("battery" in fact.lower() for fact in facts))
        self.assertTrue(any("motor" in fact.lower() for fact in facts))

    def test_query_unknown_keyword(self) -> None:
        """Graph should return an empty list for unknown keywords."""
        self.assertEqual(self.graph.query_graph("What is the range?"), [])


class TestChatbot(unittest.TestCase):
    """Test cases for the Chatbot class."""

    def setUp(self) -> None:
        self.bot = Chatbot()

    def test_new_conversation_generates_id(self) -> None:
        """A new conversation should return a unique identifier."""
        result = self.bot.process_chat_request("How does the battery work?")
        self.assertIn("conversation_id", result)
        self.assertIn("response", result)
        self.assertTrue(result["conversation_id"] in self.bot.histories)

    def test_conversation_history_persistence(self) -> None:
        """Chatbot should maintain history across requests with the same ID."""
        result1 = self.bot.process_chat_request("Tell me about the battery.")
        cid = result1["conversation_id"]
        # Ask a second question in the same conversation.
        result2 = self.bot.process_chat_request("And what about the motor?", conversation_id=cid)
        # History should contain two user messages and two assistant messages.
        history = self.bot.histories[cid]
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[2]["role"], "user")
        self.assertEqual(history[3]["role"], "assistant")

    def test_clear_conversation_history(self) -> None:
        """Clearing a conversation should remove its history and return True."""
        result = self.bot.process_chat_request("Test clearing functionality.")
        cid = result["conversation_id"]
        self.assertTrue(self.bot.clear_conversation_history(cid))
        self.assertNotIn(cid, self.bot.histories)
        # Clearing again should return False.
        self.assertFalse(self.bot.clear_conversation_history(cid))


if __name__ == "__main__":
    unittest.main()
