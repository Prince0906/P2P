"""
API Module - REST API for P2P Node

Provides HTTP endpoints for controlling the P2P node.
"""

from .rest import create_app, run_api_server

__all__ = ['create_app', 'run_api_server']



