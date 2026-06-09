"""
Base Agent
==========
Foundation class for all AI agents in the iBank system.
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all iBank AI agents.
    
    Each agent has:
    - A specific role and expertise
    - Access to LLM for reasoning
    - A decision journal for learning
    - Learnable parameters that adapt over time
    """

    def __init__(
        self,
        name: str,
        role: str,
        openai_client=None,
        model: str = "gpt-4o",
    ):
        self.name = name
        self.role = role
        self.client = openai_client
        self.model = model

        # Learnable parameters
        self.parameters: Dict[str, Any] = {}
        self.weight: float = 1.0
        self.confidence: float = 0.5

        # Performance tracking
        self.decisions_made: int = 0
        self.correct_decisions: int = 0
        self.accuracy: float = 0.0
        self.recent_performance: list = []  # last N decisions

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass

    @abstractmethod
    def analyze(self, ticker: str, market_data: Dict, news_data: Dict, portfolio: Dict, learning_context: str = "") -> Dict:
        """
        Perform analysis and return a recommendation.
        
        Returns:
            Dict with keys:
                - action: BUY / SELL / HOLD
                - confidence: 0.0 to 1.0
                - reasoning: str
                - target_price: Optional[float]
                - stop_loss: Optional[float]
                - risk_level: LOW / MEDIUM / HIGH
                - details: Dict (agent-specific)
        """
        pass

    def query_llm(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send a query to the LLM and get a response."""
        if not self.client:
            return self._fallback_response(prompt)

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({"role": "system", "content": self.get_system_prompt()})

            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"LLM query error for {self.name}: {e}")
            return self._fallback_response(prompt)

    def _fallback_response(self, prompt: str) -> str:
        """Fallback when LLM is not available."""
        return json.dumps({
            "action": "HOLD",
            "confidence": 0.0,
            "reasoning": "LLM unavailable - defaulting to HOLD for safety",
            "risk_level": "HIGH",
        })

    def parse_json_response(self, response: str) -> Dict:
        """Parse JSON from LLM response, handling formatting issues."""
        try:
            # Try direct parse
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # Try to find JSON object
            brace_match = re.search(r'\{[\s\S]*\}', response)
            if brace_match:
                try:
                    return json.loads(brace_match.group(0))
                except json.JSONDecodeError:
                    pass

            logger.error(f"Could not parse JSON from response: {response[:200]}")
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reasoning": "Failed to parse response",
                "risk_level": "HIGH",
            }

    def update_performance(self, was_correct: bool):
        """Update agent's performance tracking."""
        self.decisions_made += 1
        if was_correct:
            self.correct_decisions += 1

        self.accuracy = self.correct_decisions / max(self.decisions_made, 1)
        self.recent_performance.append({
            "correct": was_correct,
            "timestamp": datetime.now().isoformat(),
        })

        # Keep only last 50 decisions
        if len(self.recent_performance) > 50:
            self.recent_performance = self.recent_performance[-50:]

    def adjust_parameters(self, feedback: Dict):
        """
        Adjust learnable parameters based on feedback.
        This is the core auto-learning mechanism.
        """
        if not feedback:
            return

        # Adjust weight based on accuracy
        accuracy = feedback.get("accuracy", self.accuracy)
        if accuracy > 0.65:
            self.weight = min(self.weight * 1.05, 2.0)  # Increase influence
        elif accuracy < 0.45:
            self.weight = max(self.weight * 0.95, 0.3)  # Decrease influence

        # Adjust confidence calibration
        overconfidence = feedback.get("avg_confidence", 0.5) - accuracy
        if overconfidence > 0.15:
            # Agent was overconfident — reduce confidence
            self.confidence = max(self.confidence - 0.05, 0.1)

        logger.info(f"[{self.name}] Performance update: accuracy={accuracy:.2f}, weight={self.weight:.2f}")

    def get_status(self) -> Dict:
        """Get current agent status."""
        return {
            "name": self.name,
            "role": self.role,
            "weight": round(self.weight, 3),
            "accuracy": round(self.accuracy, 3),
            "decisions_made": self.decisions_made,
            "parameters": self.parameters,
        }

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name} (accuracy={self.accuracy:.2f}, weight={self.weight:.2f})>"
