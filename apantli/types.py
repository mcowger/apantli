
from typing import (
    Any, Dict, List, Optional, Union, Type
)
from pydantic import BaseModel
from typing_extensions import Literal
from litellm import (
    ChatCompletionModality, 
    ChatCompletionPredictionContentParam, 
    ChatCompletionAudioParam, 
    OpenAIWebSearchOptions, 
    AnthropicThinkingParam
)


class ChatFunctionCallArgs(BaseModel):
    model: str

    # Optional OpenAI params
    messages: List[Any] = []
    timeout: Optional[Union[float, str, Any]] = None  # httpx.Timeout as Any
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = None
    stream_options: Optional[Dict[str, Any]] = None
    stop: Optional[Any] = None
    max_completion_tokens: Optional[int] = None
    max_tokens: Optional[int] = None
    modalities: Optional[List[ChatCompletionModality]] = None
    prediction: Optional[ChatCompletionPredictionContentParam] = None
    audio: Optional[ChatCompletionAudioParam] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[Dict[str, Any]] = None
    user: Optional[str] = None

    # OpenAI v1.0+ new params
    reasoning_effort: Optional[
        Literal["none", "minimal", "low", "medium", "high", "default"]
    ] = None
    verbosity: Optional[Literal["low", "medium", "high"]] = None
    response_format: Optional[Union[Dict[str, Any], Type[BaseModel]]] = None
    seed: Optional[int] = None
    tools: Optional[List[Any]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    parallel_tool_calls: Optional[bool] = None
    web_search_options: Optional[OpenAIWebSearchOptions] = None
    deployment_id: Optional[Any] = None
    extra_headers: Optional[Dict[str, Any]] = None
    safety_identifier: Optional[str] = None
    service_tier: Optional[str] = None

    # Soon-to-be deprecated params
    functions: Optional[List[Any]] = None
    function_call: Optional[str] = None

    # API/base config
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    api_key: Optional[str] = None

    # LiteLLM function params
    thinking: Optional[AnthropicThinkingParam] = None

    # Capture all extra kwargs
    class Config:
        extra = "allow"

    def to_dict(self) -> Dict[str, Any]:
        """Convert ChatFunctionCallArgs to a dictionary, excluding None values."""
        result = {}
        for field_name, field_value in self:
            if field_value is not None:
                result[field_name] = field_value
        return result


class EmbeddingFunctionCallArgs(BaseModel):
    """Arguments for embedding API calls via LiteLLM."""
    model: str
    input: Union[str, List[str], List[int], List[List[int]]]
    
    # Optional OpenAI params
    timeout: Optional[Union[float, str, Any]] = None
    user: Optional[str] = None
    dimensions: Optional[int] = None
    encoding_format: Optional[Literal["float", "base64"]] = None
    
    # API/base config - LiteLLM embedding uses api_base, not base_url
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    api_key: Optional[str] = None
    extra_headers: Optional[Dict[str, Any]] = None
    custom_llm_provider: Optional[str] = None
    
    # Capture all extra kwargs
    class Config:
        extra = "allow"

    def to_dict(self) -> Dict[str, Any]:
        """Convert EmbeddingFunctionCallArgs to a dictionary, excluding None values."""
        result = {}
        for field_name, field_value in self:
            if field_value is not None:
                result[field_name] = field_value
        return result
