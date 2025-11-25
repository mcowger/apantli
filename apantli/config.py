"""Configuration management for model routing."""

from typing import Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator, ValidationError
import json
from uuid import uuid4
from jinja2 import Environment
from apantli.log_config import logger


# Default configuration
DEFAULT_TIMEOUT = 300  # seconds
DEFAULT_RETRIES = 3    # number of retry attempts


class ConfigError(Exception):
  """Configuration validation error."""
  pass

class ProviderConfig(BaseModel):
  """Configuration for a single provider."""
  provider_name: str = Field(..., description="Alias used by clients")
  api_key: str = Field(..., alias="api_key", description="API key.  Can be env var (os.environ/VAR_NAME) or raw key")
  timeout: Optional[int] = Field(default=300, description="Request timeout override")
  num_retries: Optional[int] = Field(default=0, description="Retry count override")
  base_url: str = Field( ...,description="API Base URL")
  catwalk_name: Optional[str] = Field(None,description="key used for provider lookup into catwalk pricing index")
  custom_llm_provider: Optional[str] =  Field(None,description="override for custom llm provider")
  headers: Optional[dict] = Field(None,description="optional headers that will be sent with any request to this provider")


class ModelConfig(BaseModel):
  """Configuration for a single model."""
  model_name: str = Field(..., description="Alias used by clients")
  litellm_model: str = Field(..., description="LiteLLM model identifier")
  provider_name: str = Field(..., description="key for provider info lookup")
  costing_model: Optional[str] = Field(..., alias="costing_model", description="Identifier used for model capability & costing lookups")
  temperature: Optional[float] = None
  context_window: Optional[int] = None
  litellm_params: Dict[str, Any] = Field(
      default_factory=dict,
      description="Arbitrary LiteLLM parameters"
  )

class Config:
  """Application configuration manager."""

  def __init__(self, config_path: str = "config.jsonc"):
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
      logger.warning(f"Failed to render config template: {exc}")
      raise

  def parse_providers(self,config_data):
    providers = {}
    errors = []
    for provider_key, provider_value in config_data.get('providers', {}).items():
      # Extract model_name from top level
      provider_name = provider_key
      try:
        provider_config = ProviderConfig(
          provider_name=provider_name,
          api_key=provider_value.get('api_key'),
          timeout=provider_value.get('timeout',DEFAULT_TIMEOUT),
          num_retries=provider_value.get('num_retries',DEFAULT_RETRIES),
          base_url=provider_value.get('base_url'),
          catwalk_name=provider_value.get('catwalk_name', None),
          custom_llm_provider=provider_value.get('custom_llm_provider',None),
          headers=provider_value.get('headers',None),
        )

        providers[provider_name] = provider_config

      except ValidationError as exc:
        # Format validation errors nicely
        for error in exc.errors():
          field = error['loc'][0] if error['loc'] else 'unknown'
          message = error['msg']
          errors.append(f"Provider '{provider_name}': {field} - {message}")
      
    self.providers = providers
    logger.info(f"✓ Loaded {len(self.providers)} providers(s) from {self.config_path}")

  def parse_models(self,config_data):

      # Validate and load models
      models = {}
      errors = []

      for model_key, model_value in config_data.get('model_list', {}).items():
        # Extract model_name from top level
        model_name = model_key
        
        try:

          # Merge litellm_params with model_name
          litellm_params = model_value.get('litellm_params', {})
          model_config = ModelConfig(
            model_name=model_name,
            litellm_model=model_value.get('litellm_model'),
            costing_model=model_value.get('costing_model'),
            context_window=model_value.get('context_window'),
            litellm_params=litellm_params,
            provider_name=model_value.get("provider_name")
          )

          models[model_name] = model_config

        except ValidationError as exc:
          # Format validation errors nicely
          for error in exc.errors():
            field = error['loc'][0] if error['loc'] else 'unknown'
            message = error['msg']
            errors.append(f"Model '{model_name}': {field} - {message}")

      if errors:
        logger.warning("Configuration validation errors:")
        for error_msg in errors:
          logger.warning(f"  - {error_msg}")
        if not models:
          logger.warning("No valid models found in configuration")

      self.models = models
      logger.info(f"✓ Loaded {len(self.models)} model(s) from {self.config_path}")

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
      logger.warning(f"Config file not found: {self.config_path}")
      logger.warning("Server will start with no models configured")
      self.models = {}
    except json.JSONDecodeError as exc:
      logger.warning(f"Invalid JSON in config file: {exc}")
      self.models = {}
    except Exception as exc:
      logger.warning(f"Could not load config: {exc}")
      self.models = {}

  def get_model(self, model_name: str) -> Optional[ModelConfig]:
    """Get model configuration by name."""
    return self.models.get(model_name)

  def list_models(self) -> list:
    """List all configured model names."""
    return list(self.models.keys())

