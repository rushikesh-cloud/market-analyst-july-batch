import os
import unittest
from unittest.mock import Mock, patch

from app.resources import AzureResourceClients, ResourceSettings, SecretProvider


class ResourceSettingsTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "AZURE_KEY_VAULT_URI": "https://marketanalyst.vault.azure.net/",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_API_VERSION": "2025-04-01-preview",
            "AZURE_OPENAI_API_KEY_SECRET": "azure-openai-api-key",
            "AZURE_OPENAI_DEPLOYMENT_LUNA": "luna",
            "AZURE_OPENAI_DEPLOYMENT_TERRA": "terra",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "embedding-small",
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.cognitiveservices.azure.com/",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY_SECRET": "azure-document-intelligence-key",
            "POSTGRES_HOST": "example.postgres.database.azure.com",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "postgres",
            "POSTGRES_USER": "marketadmin",
            "AZURE_KEY_VAULT_POSTGRES_PASSWORD_SECRET": "postgres-admin-password",
        }

    def test_reads_resource_configuration_without_reading_secrets(self):
        with patch.dict(os.environ, self.environment, clear=True):
            settings = ResourceSettings.from_environment()

        self.assertEqual(settings.openai.luna_deployment, "luna")
        self.assertEqual(settings.openai.embedding_deployment, "embedding-small")
        self.assertEqual(settings.document_intelligence.key_secret_name, "azure-document-intelligence-key")
        self.assertEqual(settings.database.host, "example.postgres.database.azure.com")

    def test_requires_key_vault_configuration(self):
        environment = self.environment | {"AZURE_KEY_VAULT_URI": ""}
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "AZURE_KEY_VAULT_URI"):
                ResourceSettings.from_environment()


class ResourceClientTests(unittest.TestCase):
    def test_uses_key_vault_secrets_for_all_key_based_clients(self):
        settings = Mock()
        settings.openai.endpoint = "https://example.openai.azure.com/"
        settings.openai.api_version = "2025-04-01-preview"
        settings.openai.key_secret_name = "azure-openai-api-key"
        settings.openai.luna_deployment = "luna"
        settings.openai.terra_deployment = "terra"
        settings.openai.embedding_deployment = "embedding-small"
        settings.document_intelligence.endpoint = "https://example.cognitiveservices.azure.com/"
        settings.document_intelligence.key_secret_name = "azure-document-intelligence-key"
        settings.database.host = "example.postgres.database.azure.com"
        settings.database.port = 5432
        settings.database.name = "postgres"
        settings.database.user = "marketadmin"
        settings.database.password_secret_name = "postgres-admin-password"
        settings.database.sslmode = "require"
        secrets = Mock(spec=SecretProvider)
        secrets.get.side_effect = ["openai-key", "document-key", "db-password"]

        with patch("app.resources.AzureOpenAI") as openai, patch(
            "app.resources.DocumentIntelligenceClient"
        ) as document_intelligence:
            clients = AzureResourceClients(settings, secrets)
            self.assertIs(clients.openai(), openai.return_value)
            self.assertIs(clients.document_intelligence(), document_intelligence.return_value)

        self.assertEqual(secrets.get.call_args_list[0].args, ("azure-openai-api-key",))
        self.assertEqual(secrets.get.call_args_list[1].args, ("azure-document-intelligence-key",))
        self.assertIn("db-password", clients.database_url())
        self.assertIn("sslmode=require", clients.database_url())
