"""
Simplified Neo4j graph interface for the refactored DSD project.

This module defines a ``Neo4jGraph`` class that emulates basic graph
retrieval functionality without requiring a running Neo4j server.  The goal
is to provide a mockable interface for retrieving domain knowledge that can
be easily swapped out for a real graph database in future iterations.  The
underlying data structure is a dictionary mapping keywords to facts.  When
``query_graph`` is called with a question, the method performs a naive
keyword search to return relevant facts.

The data included here is purely illustrative and can be adapted to fit
real use cases.  For example, one might load facts about vehicle
components, repair procedures, or configuration options.  The lookup
behaviour can also be replaced with a call into ``neo4j`` or ``py2neo``
drivers to run Cypher queries against a live database.
"""

from __future__ import annotations

from typing import List, Dict


class Neo4jGraph:
    """Stub implementation of a Neo4j knowledge graph.

    This class stores a small amount of domain knowledge in a simple
    dictionary.  Queries are executed via a case‑insensitive keyword
    lookup.  The interface mirrors the read‑only behaviour of a real
    Neo4j client and can be extended to include write operations if
    necessary.
    """

    def __init__(self) -> None:
        # A minimal collection of facts keyed by keywords for demonstration.
        self._knowledge: Dict[str, List[str]] = {
            "battery": [
                "The battery stores electrical energy for the vehicle.",
                "A weak battery may cause starting issues."
            ],
            "charger": [
                "The charger converts AC power to DC for charging the battery.",
                "Chargers vary in power output and charging speed."
            ],
            "motor": [
                "The electric motor drives the vehicle's wheels.",
                "Electric motors provide instant torque."
            ],
            "maintenance": [
                "Regular maintenance ensures optimal performance.",
                "Check fluid levels and tire pressure regularly."
            ],
        }

    def query_graph(self, question: str) -> List[str]:
        """Retrieve facts from the knowledge graph matching keywords in the question.

        Parameters
        ----------
        question:
            The user's query string.

        Returns
        -------
        list
            A list of facts that were associated with keywords found in the
            question.  If no keywords match, an empty list is returned.
        """
        lower_question = question.lower()
        matches: List[str] = []
        for keyword, facts in self._knowledge.items():
            if keyword in lower_question:
                matches.extend(facts)
        return matches
