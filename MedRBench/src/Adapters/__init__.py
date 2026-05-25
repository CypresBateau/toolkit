"""
MedRBench 适配器模块

提供与外部工具库（如 MToolHub）的集成接口
"""

from .toolkit_adapter import ToolkitAdapter, ExperimentConfig

__all__ = ["ToolkitAdapter", "ExperimentConfig"]
