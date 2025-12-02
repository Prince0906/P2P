"""
Storage Module - Persistent Metadata Storage

Uses SQLite for storing node state and metadata.
"""

from .database import Database, init_database

__all__ = ['Database', 'init_database']



