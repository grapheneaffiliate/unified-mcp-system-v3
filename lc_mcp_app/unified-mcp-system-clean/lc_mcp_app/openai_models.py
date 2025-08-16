"""
OpenAI-compatible API models and response generation.
"""

import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Union
from pydantic import BaseModel, Field
import orjson

from .config import settings
from .observability.logging import get_logger

logger = get_logger("openai_models")


class ChatMessage(BaseModel):
    """OpenAI chat message model."""
    role: str = Field(..., description="Message role: system, user, assistant, or tool")
    content: Union[str, List[Dict[str, Any]], None] = Field(..., description="Message content")
    name: Optional[str] = Field(None, description="Optional name for the message")
    tool_call_id: Optional[str] = Field(None, description="Tool call ID for tool messages")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls in assistant messages")


class ChatCompletionRequest(BaseModel):
    """OpenAI chat completion request model."""
    model: str = Field(..., description="Model to use for completion")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    temperature: Optional[float] = Field(None, description="Sampling temperature")
    top_p: Optional[float] = Field(None, description="Nucleus sampling parameter")
    n: Optional[int] = Field(1, description="Number of completions to generate")
    stream: Optional[bool] = Field(False, description="Whether to stream responses")
    stop: Optional[Union[str, List[str]]] = Field(None, description="Stop sequences")
    presence_penalty: Optional[float] = Field(None, description="Presence penalty")
    frequency_penalty: Optional[float] = Field(None, description="Frequency penalty")
    logit_bias: Optional[Dict[str, float]] = Field(None, description="Logit bias")
    user: Optional[str] = Field(None, description="User identifier")


class ChatCompletionChoice(BaseModel):
    """OpenAI chat completion choice."""
    index: int
    message: Optional[ChatMessage] = None
    delta: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    """OpenAI chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[Dict[str, int]] = None


class ChatCompletionChunk(BaseModel):
    """OpenAI chat completion streaming chunk."""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatCompletionChoice]


class ModelInfo(BaseModel):
    """OpenAI model information."""
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelListResponse(BaseModel):
    """OpenAI model list response."""
    object: str = "list"
    data: List[ModelInfo]


async def create_streaming_response(
    messages: List[Dict[str, Any]], 
    model: str,
    request_id: Optional[str] = None
) -> AsyncIterator[bytes]:
    """Create streaming chat completion response."""
    if request_id is None:
        request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    
    created = int(time.time())
    
    # This is a placeholder - replace with actual agent streaming logic
    response_text = "Hello from LC MCP App! This is a streaming response."
    
    # Stream each character
    for i, char in enumerate(response_text):
        chunk = ChatCompletionChunk(
            id=request_id,
            created=created,
            model=model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    delta={"content": char} if char else {},
                    finish_reason=None
                )
            ]
        )
        
        chunk_json = orjson.dumps(chunk.dict())
        yield b"data: " + chunk_json + b"\n\n"
        
        # Small delay to simulate streaming
        import asyncio
        await asyncio.sleep(0.01)
    
    # Send final chunk with finish_reason
    final_chunk = ChatCompletionChunk(
        id=request_id,
        created=created,
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                delta={},
                finish_reason="stop"
            )
        ]
    )
    
    final_chunk_json = orjson.dumps(final_chunk.dict())
    yield b"data: " + final_chunk_json + b"\n\n"
    yield b"data: [DONE]\n\n"


def create_non_streaming_response(
    messages: List[Dict[str, Any]], 
    model: str,
    request_id: Optional[str] = None
) -> ChatCompletionResponse:
    """Create non-streaming chat completion response."""
    if request_id is None:
        request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    
    created = int(time.time())
    
    # This is a placeholder - replace with actual agent logic
    response_content = "Hello from LC MCP App! This is a non-streaming response."
    
    return ChatCompletionResponse(
        id=request_id,
        created=created,
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(
                    role="assistant",
                    content=response_content
                ),
                finish_reason="stop"
            )
        ],
        usage={
            "prompt_tokens": 0,  # Calculate actual tokens
            "completion_tokens": 0,  # Calculate actual tokens
            "total_tokens": 0  # Calculate actual tokens
        }
    )


def get_available_models() -> ModelListResponse:
    """Get list of available models."""
    models = [
        ModelInfo(
            id=settings.openai_default_model,
            created=int(time.time()),
            owned_by="lc-mcp-app"
        )
    ]
    
    # Add configured model if different
    if settings.openai_model_name != settings.openai_default_model:
        models.append(
            ModelInfo(
                id=settings.openai_model_name,
                created=int(time.time()),
                owned_by="lc-mcp-app"
            )
        )
    
    return ModelListResponse(data=models)


def validate_chat_request(request: ChatCompletionRequest) -> None:
    """Validate chat completion request."""
    if not request.messages:
        raise ValueError("Messages cannot be empty")
    
    if request.max_tokens is not None and request.max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    
    if request.temperature is not None and not 0.0 <= request.temperature <= 2.0:
        raise ValueError("temperature must be between 0.0 and 2.0")
    
    if request.top_p is not None and not 0.0 <= request.top_p <= 1.0:
        raise ValueError("top_p must be between 0.0 and 1.0")
    
    if request.n is not None and request.n <= 0:
        raise ValueError("n must be positive")


def extract_user_message(messages: List[ChatMessage]) -> str:
    """Extract the latest user message for agent processing."""
    for message in reversed(messages):
        if message.role == "user" and isinstance(message.content, str):
            return message.content
    
    # Fallback
    return "No user message found"


def format_chat_history(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    """Format messages for agent consumption."""
    formatted = []
    
    for message in messages[:-1]:  # Exclude last message (current user input)
        if message.role in ["user", "assistant", "system"]:
            formatted.append({
                "role": message.role,
                "content": message.content
            })
    
    return formatted


def calculate_token_usage(
    prompt: str, 
    completion: str, 
    model: str
) -> Dict[str, int]:
    """Calculate token usage (placeholder implementation)."""
    # This is a simplified calculation
    # In production, use tiktoken or similar for accurate counting
    prompt_tokens = len(prompt.split()) * 1.3  # Rough approximation
    completion_tokens = len(completion.split()) * 1.3
    
    return {
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(prompt_tokens + completion_tokens)
    }
