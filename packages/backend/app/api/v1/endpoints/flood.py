# packages/backend/app/api/v1/endpoints/flood.py
from fastapi import APIRouter
from typing import List, Optional

router = APIRouter()

@router.get("/status")
async def get_flood_status():
    """Get flood SCADA system status"""
    return {
        "status": "success",
        "message": "Flood SCADA system operational",
        "gates": [
            {"id": 1, "name": "Barrage A", "location": "Tarbela", "status": "closed", "water_level": 12.5},
            {"id": 2, "name": "Barrage B", "location": "Mangla", "status": "open", "water_level": 8.3},
            {"id": 3, "name": "Barrage C", "location": "Chashma", "status": "closed", "water_level": 6.7},
        ]
    }

@router.get("/gates")
async def get_gates():
    """Get all gate statuses"""
    return {
        "status": "success",
        "gates": [
            {"id": 1, "name": "Gate 1", "position": 0, "target": 0, "mode": "auto"},
            {"id": 2, "name": "Gate 2", "position": 50, "target": 50, "mode": "manual"},
            {"id": 3, "name": "Gate 3", "position": 100, "target": 100, "mode": "auto"},
        ]
    }

@router.post("/gates/{gate_id}/control")
async def control_gate(gate_id: int, action: str):
    """Control a gate (open/close)"""
    return {
        "status": "success",
        "message": f"Gate {gate_id} {action} command sent",
        "gate_id": gate_id,
        "action": action
    }