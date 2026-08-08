"""Individual agent implementations."""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from anthropic import Anthropic

from .models import AgentDecision, AgentRole, ResearchTask, ResearchState


class BaseAgent(ABC):
    """Base class for research agents."""

    def __init__(self, role: AgentRole, model: str = "claude-opus-5"):
        self.role = role
        self.model = model
        self.client = Anthropic()
        self.conversation_history: list[dict[str, str]] = []

    @abstractmethod
    def execute(
        self, task: ResearchTask, context: Optional[ResearchState] = None
    ) -> AgentDecision:
        """Execute the agent's task."""
        pass

    def _call_claude(self, system: str, user_message: str) -> str:
        """Call Claude API and maintain conversation history."""
        self.conversation_history.append({"role": "user", "content": user_message})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=self.conversation_history,
        )

        assistant_message = response.content[0].text
        self.conversation_history.append(
            {"role": "assistant", "content": assistant_message}
        )

        return assistant_message

    def clear_history(self):
        """Clear conversation history for new task."""
        self.conversation_history = []


class ResearcherAgent(BaseAgent):
    """Agent responsible for researching the query."""

    def __init__(self, model: str = "claude-opus-5"):
        super().__init__(AgentRole.RESEARCHER, model)

    def execute(
        self, task: ResearchTask, context: Optional[ResearchState] = None
    ) -> AgentDecision:
        """Research the given query and gather information."""
        self.clear_history()

        system_prompt = """You are an expert research agent. Your role is to:
1. Thoroughly research the given query
2. Identify credible sources and information
3. Synthesize findings into a comprehensive research report
4. Provide evidence-based insights
5. Rate your confidence in the findings (0.0 to 1.0)

Format your response as JSON with keys: content, confidence, reasoning"""

        user_prompt = f"""Research the following query:
Query: {task.query}
Description: {task.description or 'No additional description'}
Research Depth: {task.research_depth}
Required Sources: {', '.join(task.required_sources) if task.required_sources else 'Any credible sources'}

{f'Previous iteration context: {context.researcher_decision.content[:500]}...' if context and context.researcher_decision else ''}

Provide a comprehensive research report."""

        response = self._call_claude(system_prompt, user_prompt)

        try:
            data = json.loads(response)
            content = data.get("content", response)
            confidence = data.get("confidence", 0.8)
            reasoning = data.get("reasoning", "Research completed based on available sources")
        except json.JSONDecodeError:
            content = response
            confidence = 0.75
            reasoning = "Research completed"

        return AgentDecision(
            agent_role=AgentRole.RESEARCHER,
            content=content,
            confidence=float(confidence),
            reasoning=reasoning,
            metadata={"research_depth": task.research_depth},
        )


class WriterAgent(BaseAgent):
    """Agent responsible for writing the final output."""

    def __init__(self, model: str = "claude-opus-5"):
        super().__init__(AgentRole.WRITER, model)

    def execute(
        self, task: ResearchTask, context: Optional[ResearchState] = None
    ) -> AgentDecision:
        """Write polished output based on research."""
        self.clear_history()

        system_prompt = """You are an expert writer and communicator. Your role is to:
1. Create clear, engaging written content based on research findings
2. Structure information logically
3. Ensure clarity and accessibility for the target audience
4. Maintain factual accuracy from source materials
5. Rate your confidence in the written output (0.0 to 1.0)

Format your response as JSON with keys: content, confidence, reasoning"""

        research_context = (
            f"Research findings:\n{context.researcher_decision.content[:1000]}"
            if context and context.researcher_decision
            else "No prior research available"
        )

        user_prompt = f"""Based on the following research, write a polished final output:
Query: {task.query}

{research_context}

Write a comprehensive, well-structured article or report that communicates the findings clearly and effectively."""

        response = self._call_claude(system_prompt, user_prompt)

        try:
            data = json.loads(response)
            content = data.get("content", response)
            confidence = data.get("confidence", 0.8)
            reasoning = data.get("reasoning", "Writing completed")
        except json.JSONDecodeError:
            content = response
            confidence = 0.75
            reasoning = "Writing completed"

        return AgentDecision(
            agent_role=AgentRole.WRITER,
            content=content,
            confidence=float(confidence),
            reasoning=reasoning,
            metadata={"structured": True},
        )


class FactCheckerAgent(BaseAgent):
    """Agent responsible for fact-checking the output."""

    def __init__(self, model: str = "claude-opus-5"):
        super().__init__(AgentRole.FACT_CHECKER, model)

    def execute(
        self, task: ResearchTask, context: Optional[ResearchState] = None
    ) -> AgentDecision:
        """Verify facts and check for accuracy."""
        self.clear_history()

        system_prompt = """You are an expert fact-checker and quality assurance agent. Your role is to:
1. Verify factual accuracy of claims
2. Check for logical consistency
3. Identify unsupported claims or gaps
4. Assess the overall quality and reliability
5. Provide specific feedback and recommendations
6. Rate your confidence in the verification (0.0 to 1.0)

Format your response as JSON with keys: content, confidence, reasoning, issues_found"""

        writer_content = (
            context.writer_decision.content[:1000] if context and context.writer_decision
            else "No writing available"
        )

        researcher_context = (
            context.researcher_decision.content[:1000]
            if context and context.researcher_decision
            else ""
        )

        user_prompt = f"""Fact-check the following written output against the research:
Query: {task.query}

Research Summary:
{researcher_context}

Written Output:
{writer_content}

Provide a comprehensive fact-check report with any issues found and recommendations."""

        response = self._call_claude(system_prompt, user_prompt)

        try:
            data = json.loads(response)
            content = data.get("content", response)
            confidence = data.get("confidence", 0.85)
            reasoning = data.get("reasoning", "Fact-check completed")
            issues_found = data.get("issues_found", [])
        except json.JSONDecodeError:
            content = response
            confidence = 0.75
            reasoning = "Fact-check completed"
            issues_found = []

        return AgentDecision(
            agent_role=AgentRole.FACT_CHECKER,
            content=content,
            confidence=float(confidence),
            reasoning=reasoning,
            metadata={"issues_found": issues_found, "verification_complete": True},
        )
