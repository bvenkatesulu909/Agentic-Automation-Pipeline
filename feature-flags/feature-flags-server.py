#!/usr/bin/env python3
"""
Feature flags server for ADK Agents.
Serves feature flag configuration with support for rollouts and experimentation.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel


class FeatureFlag(BaseModel):
    name: str
    type: str
    enabled: bool
    rolloutPercentage: int
    rules: List[Dict[str, Any]] = []
    environment: str
    description: str
    createdAt: str
    modifiedAt: str
    modifiedBy: str


class FlagsResponse(BaseModel):
    flags: List[FeatureFlag]
    timestamp: str
    environment: str


app = FastAPI(title="Feature Flags Server")

# Load flags from ConfigMap
FEATURES_FILE = os.getenv("FEATURES_FILE", "/etc/feature-flags/rollouts.json")


def load_flags() -> Dict[str, Any]:
    """Load feature flags from file."""
    try:
        with open(FEATURES_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"flags": []}


def should_enable_flag(flag: Dict[str, Any], user_id: Optional[str] = None) -> bool:
    """Determine if a flag should be enabled for a user."""
    if not flag.get("enabled"):
        return False

    rollout = flag.get("rolloutPercentage", 0)
    if rollout < 100:
        if user_id:
            # Hash-based rollout consistency
            hash_val = hash(f"{user_id}:{flag['name']}") % 100
            return hash_val < rollout
        else:
            # Default to rollout percentage without user context
            return False

    return True


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/flags", response_model=FlagsResponse)
async def get_flags(
    environment: str = Query("production"),
    user_id: Optional[str] = Query(None),
):
    """Get feature flags for the specified environment."""
    flags_data = load_flags()
    all_flags = flags_data.get("flags", [])

    # Filter flags by environment
    relevant_flags = [
        f for f in all_flags
        if f.get("environment") in (environment, "all")
    ]

    # Evaluate rollouts for each flag
    evaluated_flags = []
    for flag in relevant_flags:
        flag_copy = flag.copy()
        flag_copy["enabled"] = should_enable_flag(flag, user_id)
        evaluated_flags.append(FeatureFlag(**flag_copy))

    return FlagsResponse(
        flags=evaluated_flags,
        timestamp=datetime.utcnow().isoformat() + "Z",
        environment=environment,
    )


@app.get("/api/flags/{flag_name}")
async def get_flag(
    flag_name: str,
    environment: str = Query("production"),
    user_id: Optional[str] = Query(None),
):
    """Get a specific feature flag."""
    flags_data = load_flags()
    all_flags = flags_data.get("flags", [])

    flag = next(
        (f for f in all_flags if f.get("name") == flag_name),
        None,
    )

    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")

    if flag.get("environment") not in (environment, "all"):
        raise HTTPException(status_code=404, detail="Flag not found for this environment")

    enabled = should_enable_flag(flag, user_id)

    return {
        "name": flag_name,
        "enabled": enabled,
        "environment": environment,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/api/flags/{flag_name}/rollout")
async def update_rollout(
    flag_name: str,
    percentage: int = Query(..., ge=0, le=100),
):
    """Update rollout percentage for a flag (requires auth in production)."""
    if not (0 <= percentage <= 100):
        raise HTTPException(status_code=400, detail="Percentage must be 0-100")

    flags_data = load_flags()
    all_flags = flags_data.get("flags", [])

    flag = next(
        (f for f in all_flags if f.get("name") == flag_name),
        None,
    )

    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")

    flag["rolloutPercentage"] = percentage
    flag["modifiedAt"] = datetime.utcnow().isoformat() + "Z"
    flag["modifiedBy"] = "api"

    # In production, persist changes
    with open(FEATURES_FILE, "w") as f:
        json.dump(flags_data, f, indent=2)

    return {
        "name": flag_name,
        "rolloutPercentage": percentage,
        "message": "Rollout updated successfully",
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    # Simple implementation - can be enhanced with actual metrics
    flags_data = load_flags()
    flag_count = len(flags_data.get("flags", []))

    return {
        "feature_flags_total": flag_count,
        "feature_flags_enabled": sum(1 for f in flags_data.get("flags", []) if f.get("enabled")),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
