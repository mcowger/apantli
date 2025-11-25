"""Configuration management for model routing."""

import os
import logging
import warnings
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator, ValidationError
import json
from uuid import uuid4
from jinja2 import Environment


# Default configuration
DEFAULT_TIMEOUT = 120  # seconds
DEFAULT_RETRIES = 3    # number of retry attempts

# Log alignment constant to match uvicorn INFO log format
# Format: "2025-10-11 14:16:31 INFO:     message"
#         └─────────┴────────┴─────────┘
#         11 chars + 9 chars + 8 chars = 28 chars
LOG_INDENT = " " * 28


class ConfigError(Exception):
  """Configuration validation error."""
  pass

class ProviderConfig(BaseModel):
  """Configuration for a single provider."""
  provider_name: str = Field(..., description="Alias used by clients")
  api_key: str = Field(..., alias="api_key", description="API key.  Can be env var (os.environ/VAR_NAME) or raw key")
  timeout: Optional[int] = Field(None, description="Request timeout override")
  num_retries: Optional[int] = Field(None, description="Retry count override")
  base_url: str = Field(None,description="API Base URL")
  catwalk_name: Optional[str] = Field(None,description="key used for provider lookup into catwalk pricing index")
  custom_llm_provider: Optional[str] =  Field(None,description="override for custom llm provider")
  headers: Optional[dict] = Field(None,description="optional headers that will be sent with any request to this provider")


class ModelConfig(BaseModel):
  """Configuration for a single model."""
  model_name: str = Field(..., description="Alias used by clients")
  litellm_model: str = Field(..., alias="model", description="LiteLLM model identifier")
  provider_name: str = Field(..., alias="provider_name", description="key for provider info lookup")
  costing_model: Optional[str] = Field(..., alias="costing_model", description="Identifier used for model capability & costing lookups")
  temperature: Optional[float] = None
  max_tokens: Optional[int] = None
  litellm_params: Dict[str, Any] = Field(
      default_factory=dict,
      description="Arbitrary LiteLLM parameters"
  )

class Config:
  """Application configuration manager."""

  def __init__(self, config_path: str = "config.json.jinja"):
    self.config_path = config_path
    self.models: Dict[str, ModelConfig] = {}
    self.providers: Dict[str, ProviderConfig] = {}
    self.reload()

  def _render_template(self) -> str:
    """Render the config file as a Jinja2 template.

    Returns the rendered JSON content as a string.
    """
    try:
      # Read the raw config file
      with open(self.config_path, 'r') as f:
        template_content = f.read()

      # Create a Jinja2 environment to render the template
      env = Environment()
      template = env.from_string(template_content)

      rendered = template.render(uuid=uuid4)

      return rendered

    except Exception as exc:
      logging.warning(f"Failed to render config template: {exc}")
      raise

  def parse_providers(self,config_data):
    providers = {}
    errors = []
    for provider_dict in config_data.get('provider_list', []):
      # Extract model_name from top level
      provider_name = provider_dict.get('provider_name', 'unknown')
      
      try:
        if not provider_dict.get('provider_name'):
          errors.append("Provider entry missing 'provider_name' field")
          continue

        # Merge litellm_params with model_name

        provider_config = ProviderConfig(
          provider_name=provider_name,
          api_key=provider_dict.get('api_key'),
          timeout=provider_dict.get('timeout',DEFAULT_TIMEOUT),
          num_retries=provider_dict.get('num_retries',DEFAULT_RETRIES),
          base_url=provider_dict.get('base_url'),
        )
        if provider_dict.get("catwalk_name",None):
          provider_config.catwalk_name=provider_dict.get("catwalk_name")
        if provider_dict.get("custom_llm_provider",None):
          provider_config.custom_llm_provider=provider_dict.get("custom_llm_provider")
        if provider_dict.get("headers",None):
          provider_config.headers=provider_dict.get("headers")

        providers[provider_name] = provider_config

      except ValidationError as exc:
        # Format validation errors nicely
        for error in exc.errors():
          field = error['loc'][0] if error['loc'] else 'unknown'
          message = error['msg']
          errors.append(f"Provider '{provider_name}': {field} - {message}")
      
    self.providers = providers

    if providers:
      logging.info(f"{LOG_INDENT}✓ Loaded {len(self.providers)} model(s) from {self.config_path}")

  def parse_models(self,config_data):

      # Validate and load models
      models = {}
      errors = []

      for model_dict in config_data.get('model_list', []):
        # Extract model_name from top level
        model_name = model_dict.get('model_name', 'unknown')
        
        try:
          if not model_dict.get('model_name'):
            errors.append("Model entry missing 'model_name' field")
            continue

          # Merge litellm_params with model_name
          litellm_params = model_dict.get('litellm_params', {})
          model_config = ModelConfig(
            model_name=model_name,
            costing_model=model_dict.get('costing_model'),
            litellm_params=litellm_params,
            provider_name=model_dict.get("provider_name")
          )

          models[model_name] = model_config

        except ValidationError as exc:
          # Format validation errors nicely
          for error in exc.errors():
            field = error['loc'][0] if error['loc'] else 'unknown'
            message = error['msg']
            errors.append(f"Model '{model_name}': {field} - {message}")

      if errors:
        logging.warning("Configuration validation errors:")
        for error_msg in errors:
          logging.warning(f"  - {error_msg}")
        if not models:
          logging.warning("No valid models found in configuration")

      self.models = models

      if models:
        logging.info(f"{LOG_INDENT}✓ Loaded {len(self.models)} model(s) from {self.config_path}")

  def reload(self):
    """Load or reload configuration from file."""
    try:
      # Render the config file as a Jinja2 template first
      rendered_config = self._render_template()
      # Parse the rendered JSON
      config_data = json.loads(rendered_config)
      self.parse_providers(config_data=config_data)
      self.parse_models(config_data=config_data)

    except FileNotFoundError:
      logging.warning(f"Config file not found: {self.config_path}")
      logging.warning("Server will start with no models configured")
      self.models = {}
    except json.JSONDecodeError as exc:
      logging.warning(f"Invalid JSON in config file: {exc}")
      self.models = {}
    except Exception as exc:
      logging.warning(f"Could not load config: {exc}")
      self.models = {}

  def get_model(self, model_name: str) -> Optional[ModelConfig]:
    """Get model configuration by name."""
    return self.models.get(model_name)

  def list_models(self) -> list:
    """List all configured model names."""
    return list(self.models.keys())

  def get_model_map(self, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, dict]:
    """Get all models as a dict mapping names to litellm parameters.

    Args:
      defaults: Default values for timeout, num_retries, etc.

    Returns:
      Dict mapping model names to litellm_params dicts
    """
    return {
      name: model.to_litellm_params(defaults)
      for name, model in self.models.items()
    }
