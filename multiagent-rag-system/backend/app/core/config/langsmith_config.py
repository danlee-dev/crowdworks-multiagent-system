"""
LangSmith Configuration for RAG Workflow Tracing

This module configures LangSmith tracing for the LangGraph workflow,
enabling full observability of the RAG system.
"""

import os
from typing import Optional, Dict, Any


def configure_langsmith(
    project_name: Optional[str] = None,
    enabled: Optional[bool] = None
) -> Dict[str, str]:
    """
    Configure LangSmith tracing environment variables.

    Args:
        project_name: LangSmith project name (defaults to env var or "crowdworks-rag-system")
        enabled: Enable tracing (defaults to env var or True if API key present)

    Returns:
        Dictionary of configured environment variables
    """
    # Get API key
    api_key = os.getenv("LANGSMITH_API_KEY")

    if not api_key:
        print("⚠️  LangSmith API key not found. Tracing will be disabled.")
        print("   Set LANGSMITH_API_KEY environment variable to enable tracing.")
        return {}

    # Determine if tracing should be enabled
    if enabled is None:
        enabled = os.getenv("LANGCHAIN_TRACING_V2", "true").lower() == "true"

    if not enabled:
        print("ℹ️  LangSmith tracing is disabled (LANGCHAIN_TRACING_V2=false)")
        return {}

    # Determine project name
    if project_name is None:
        project_name = os.getenv(
            "LANGSMITH_PROJECT",
            "crowdworks-rag-system"
        )

    # Set environment variables
    config = {
        "LANGCHAIN_TRACING_V2": "true",
        "LANGCHAIN_API_KEY": api_key,
        "LANGCHAIN_PROJECT": project_name,
        "LANGCHAIN_ENDPOINT": os.getenv(
            "LANGCHAIN_ENDPOINT",
            "https://api.smith.langchain.com"
        )
    }

    # Apply configuration
    for key, value in config.items():
        os.environ[key] = value

    print(f"✅ LangSmith tracing enabled")
    print(f"   Project: {project_name}")
    print(f"   Endpoint: {config['LANGCHAIN_ENDPOINT']}")

    return config


def add_run_tags(
    run_id: Optional[str] = None,
    flow_type: Optional[str] = None,
    persona: Optional[str] = None,
    **extra_tags
) -> Dict[str, Any]:
    """
    Create tags for LangSmith runs.

    Tags help filter and organize traces in the LangSmith UI.

    Args:
        run_id: Unique run identifier
        flow_type: Workflow type ("chat" or "task")
        persona: Selected persona/team
        **extra_tags: Additional custom tags

    Returns:
        Dictionary of tags for LangSmith metadata
    """
    tags = {}

    if run_id:
        tags["run_id"] = run_id

    if flow_type:
        tags["flow_type"] = flow_type

    if persona:
        tags["persona"] = persona

    # Add environment tag
    environment = os.getenv("ENVIRONMENT", "development")
    tags["environment"] = environment

    # Add any extra tags
    tags.update(extra_tags)

    return tags


def create_run_metadata(
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    project_id: Optional[str] = None,
    **extra_metadata
) -> Dict[str, Any]:
    """
    Create metadata for LangSmith runs.

    Metadata provides additional context for traces.

    Args:
        user_id: User identifier
        conversation_id: Conversation/session identifier
        project_id: Project identifier
        **extra_metadata: Additional custom metadata

    Returns:
        Dictionary of metadata for LangSmith
    """
    metadata = {}

    if user_id:
        metadata["user_id"] = user_id

    if conversation_id:
        metadata["conversation_id"] = conversation_id

    if project_id:
        metadata["project_id"] = project_id

    # Add system metadata
    metadata["system"] = "crowdworks-rag-system"
    metadata["version"] = "3.0-langgraph"

    # Add any extra metadata
    metadata.update(extra_metadata)

    return metadata


def get_langsmith_config() -> Dict[str, Any]:
    """
    Get current LangSmith configuration.

    Returns:
        Dictionary with configuration status and settings
    """
    api_key = os.getenv("LANGSMITH_API_KEY")
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    project = os.getenv("LANGSMITH_PROJECT", "crowdworks-rag-system")

    return {
        "enabled": tracing_enabled and bool(api_key),
        "has_api_key": bool(api_key),
        "tracing_v2": tracing_enabled,
        "project": project,
        "endpoint": os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    }


def disable_langsmith():
    """
    Temporarily disable LangSmith tracing.

    Useful for testing or when tracing is not needed.
    """
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    print("ℹ️  LangSmith tracing disabled")


def enable_langsmith(project_name: Optional[str] = None):
    """
    Enable LangSmith tracing.

    Args:
        project_name: Optional project name to use
    """
    configure_langsmith(project_name=project_name, enabled=True)


# ============================================================================
# Auto-configuration on import (if API key present)
# ============================================================================

def auto_configure():
    """
    Automatically configure LangSmith if API key is present.

    This runs when the module is imported.
    """
    # Only auto-configure if API key is present and not explicitly disabled
    api_key = os.getenv("LANGSMITH_API_KEY")
    explicit_disable = os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "false"

    if api_key and not explicit_disable:
        configure_langsmith()
    elif not api_key:
        print("ℹ️  LangSmith API key not found. Tracing disabled.")
        print("   To enable tracing:")
        print("   1. Set LANGSMITH_API_KEY in your .env file")
        print("   2. Restart the application")


# Run auto-configuration on import
auto_configure()
