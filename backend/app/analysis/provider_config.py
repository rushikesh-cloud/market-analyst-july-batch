"""Optional analysis settings do not resolve secrets during startup."""

from dataclasses import dataclass
import os

from .contracts import AgentType, AnalysisError, ErrorCode, ModelConfiguration


@dataclass(frozen=True)
class AnalysisProviderSettings:
    fundamental_deployment: str | None = None
    technical_deployment: str | None = None
    news_deployment: str | None = None
    tavily_key_secret: str | None = None

    @classmethod
    def from_environment(cls):
        def optional(name):
            return os.environ.get(name, "").strip() or None

        return cls(
            fundamental_deployment=optional("ANALYSIS_FUNDAMENTAL_DEPLOYMENT"),
            technical_deployment=optional("ANALYSIS_TECHNICAL_DEPLOYMENT"),
            news_deployment=optional("ANALYSIS_NEWS_DEPLOYMENT"),
            tavily_key_secret=optional("TAVILY_API_KEY_SECRET"),
        )

    def model_configuration(self, agent_type, openai_settings) -> ModelConfiguration:
        try:
            agent = AgentType(agent_type)
            deployment = getattr(self, f"{agent.value}_deployment") or openai_settings.terra_deployment
            return ModelConfiguration(deployment=deployment, api_version=openai_settings.api_version)
        except ValueError:
            raise AnalysisError(ErrorCode.CONFIGURATION_ERROR) from None

    def require_tavily_secret(self) -> str:
        if not self.tavily_key_secret:
            raise AnalysisError(ErrorCode.CONFIGURATION_ERROR)
        return self.tavily_key_secret
