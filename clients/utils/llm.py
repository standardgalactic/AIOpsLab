# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""An common abstraction for a cached LLM inference setup. Currently supports OpenAI's gpt-4-turbo."""

import os
import json
import yaml
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass

from openai import OpenAI
from azure.ai.ml import MLClient
from azure.identity import DefaultAzureCredential


CACHE_DIR = Path("./cache_dir")
CACHE_PATH = CACHE_DIR / "cache.json"

@dataclass
class AzureConfig:
    subscription_id: str
    resource_group_name: str
    workspace_name: str

def load_azure_config(yaml_file_path: str) -> AzureConfig:
    with open(yaml_file_path, "r") as file:
        data = yaml.safe_load(file)
        azure_config_data = data.get("azure_config", {})
        return AzureConfig(
            subscription_id=azure_config_data.get("subscription_id", ""),
            resource_group_name=azure_config_data.get("resource_group_name", ""),
            workspace_name=azure_config_data.get("workspace_name", "")
        )

class Cache:
    """A simple cache implementation to store the results of the LLM inference."""

    def __init__(self) -> None:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH) as f:
                self.cache_dict = json.load(f)
        else:
            os.makedirs(CACHE_DIR, exist_ok=True)
            self.cache_dict = {}

    @staticmethod
    def process_payload(payload):
        if isinstance(payload, (list, dict)):
            return json.dumps(payload)
        return payload

    def get_from_cache(self, payload):
        payload_cache = self.process_payload(payload)
        if payload_cache in self.cache_dict:
            return self.cache_dict[payload_cache]
        return None

    def add_to_cache(self, payload, output):
        payload_cache = self.process_payload(payload)
        self.cache_dict[payload_cache] = output

    def save_cache(self):
        with open(CACHE_PATH, "w") as f:
            json.dump(self.cache_dict, f, indent=4)


class GPT4Turbo:
    """Abstraction for OpenAI's GPT-4 Turbo model."""

    def __init__(self, auth_type: str = "key", api_key: Optional[str] = None, azure_config: Optional[AzureConfig] = None, use_cache: bool = True):
        self.cache = Cache()
        self.client = self._setup_client(auth_type, api_key, azure_config)

    def _setup_client(self, auth_type: str, api_key: Optional[str], azure_config: Optional[AzureConfig]):
        if auth_type == "key":
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("API key must be provided or set in OPENAI_API_KEY environment variable")
            return OpenAI(api_key=api_key)
        
        elif auth_type == "managed":
            azure_config = azure_config or load_azure_config("configs/example_azure_config.yml")
            if not azure_config:
                raise ValueError("Azure configuration must be provided for managed identity")
            credential = DefaultAzureCredential()
            return MLClient(credential=credential, subscription_id=azure_config.subscription_id, resource_group_name=azure_config.resource_group_name, workspace_name=azure_config.workspace_name)
        else:
            raise ValueError("auth_type must be either 'key' or 'managed'")

    def inference(self, payload: list[dict[str, str]], managed_identity: bool = False) -> list[str]:
        if self.cache is not None:
            cache_result = self.cache.get_from_cache(payload)
            if cache_result is not None:
                return cache_result

        try:
            response = self.client.chat.completions.create(
                messages=payload,  # type: ignore
                model="gpt-4-turbo-2024-04-09",
                max_tokens=1024,
                temperature=0.5,
                top_p=0.95,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                n=1,
                timeout=60,
                stop=[],
            )
        except Exception as e:
            print(f"Exception: {repr(e)}")
            raise e

        return [c.message.content for c in response.choices]  # type: ignore

    def run(self, payload: list[dict[str, str]]) -> list[str]:
        response = self.inference(payload)
        if self.cache is not None:
            self.cache.add_to_cache(payload, response)
            self.cache.save_cache()
        return response