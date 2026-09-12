"""Safe, reusable clients for the Market Analyst Azure resources."""

from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Protocol
from urllib.parse import quote

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from openai import AzureOpenAI
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be configured.")
    return value


@dataclass(frozen=True)
class OpenAISettings:
    endpoint: str
    api_version: str
    key_secret_name: str
    luna_deployment: str
    terra_deployment: str
    embedding_deployment: str


@dataclass(frozen=True)
class DocumentIntelligenceSettings:
    endpoint: str
    key_secret_name: str


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    name: str
    user: str
    password_secret_name: str
    sslmode: str


@dataclass(frozen=True)
class ResourceSettings:
    key_vault_uri: str
    openai: OpenAISettings
    document_intelligence: DocumentIntelligenceSettings
    database: DatabaseSettings

    @classmethod
    def from_environment(cls) -> "ResourceSettings":
        return cls(
            key_vault_uri=_required("AZURE_KEY_VAULT_URI"),
            openai=OpenAISettings(
                endpoint=_required("AZURE_OPENAI_ENDPOINT"),
                api_version=_required("AZURE_OPENAI_API_VERSION"),
                key_secret_name=_required("AZURE_OPENAI_API_KEY_SECRET"),
                luna_deployment=_required("AZURE_OPENAI_DEPLOYMENT_LUNA"),
                terra_deployment=_required("AZURE_OPENAI_DEPLOYMENT_TERRA"),
                embedding_deployment=_required("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
            ),
            document_intelligence=DocumentIntelligenceSettings(
                endpoint=_required("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"),
                key_secret_name=_required("AZURE_DOCUMENT_INTELLIGENCE_KEY_SECRET"),
            ),
            database=DatabaseSettings(
                host=_required("POSTGRES_HOST"),
                port=int(_required("POSTGRES_PORT")),
                name=_required("POSTGRES_DB"),
                user=_required("POSTGRES_USER"),
                password_secret_name=_required("AZURE_KEY_VAULT_POSTGRES_PASSWORD_SECRET"),
                sslmode=os.environ.get("POSTGRES_SSLMODE", "require"),
            ),
        )


class SecretProvider(Protocol):
    def get(self, name: str) -> str: ...


class KeyVaultSecretProvider:
    """Fetches and caches secrets without logging their values."""

    def __init__(self, vault_uri: str):
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self._client = SecretClient(vault_url=vault_uri, credential=credential)

    @lru_cache(maxsize=32)
    def get(self, name: str) -> str:
        value = self._client.get_secret(name).value
        if not value:
            raise RuntimeError(f"Key Vault secret {name!r} has no value.")
        return value


class AzureResourceClients:
    """Lazily creates SDK clients; application modules never receive raw secrets."""

    def __init__(self, settings: ResourceSettings, secrets: SecretProvider):
        self.settings = settings
        self.secrets = secrets
        self._openai: AzureOpenAI | None = None
        self._document_intelligence: DocumentIntelligenceClient | None = None
        self._database_url: str | None = None

    def openai(self) -> AzureOpenAI:
        if self._openai is None:
            self._openai = AzureOpenAI(
                api_key=self.secrets.get(self.settings.openai.key_secret_name),
                api_version=self.settings.openai.api_version,
                azure_endpoint=self.settings.openai.endpoint,
            )
        return self._openai

    def document_intelligence(self) -> DocumentIntelligenceClient:
        if self._document_intelligence is None:
            self._document_intelligence = DocumentIntelligenceClient(
                endpoint=self.settings.document_intelligence.endpoint,
                credential=AzureKeyCredential(
                    self.secrets.get(self.settings.document_intelligence.key_secret_name)
                ),
            )
        return self._document_intelligence

    def database_url(self) -> str:
        if self._database_url is not None:
            return self._database_url
        database = self.settings.database
        password = quote(self.secrets.get(database.password_secret_name), safe="")
        user = quote(database.user, safe="")
        self._database_url = (
            f"postgresql+psycopg://{user}:{password}@{database.host}:{database.port}/"
            f"{database.name}?sslmode={database.sslmode}"
        )
        return self._database_url

    def database_engine(self) -> Engine:
        return create_engine(self.database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_resource_clients() -> AzureResourceClients:
    settings = ResourceSettings.from_environment()
    return AzureResourceClients(settings, KeyVaultSecretProvider(settings.key_vault_uri))
