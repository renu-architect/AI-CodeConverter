"""Agent registry — maps workflow stages to agent instances."""

from agents.base_agent import BaseAgent


class AgentRegistry:
    """Maps stage names to agent instances. Only orchestrator uses this."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, stage: str, agent: BaseAgent) -> None:
        self._agents[stage] = agent

    def get(self, stage: str) -> BaseAgent:
        if stage not in self._agents:
            raise KeyError(f"No agent registered for stage: {stage}")
        return self._agents[stage]

    def list_stages(self) -> list[str]:
        return list(self._agents.keys())

    def has(self, stage: str) -> bool:
        return stage in self._agents
