"""
Configuration Management

Handles loading configuration from environment variables and config files.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import json

from dotenv import load_dotenv


@dataclass
class Config:
    """
    P2P Node Configuration.
    
    Configuration priority (highest to lowest):
    1. Environment variables (P2P_*)
    2. Config file (config.json)
    3. Default values
    """
    # Network
    host: str = '0.0.0.0'
    dht_port: int = 8468
    transfer_port: int = 8469
    api_port: int = 8080
    
    # Storage
    data_dir: Path = field(default_factory=lambda: Path('./p2p_data'))
    
    # Discovery
    auto_discover: bool = True
    bootstrap_nodes: List[Tuple[str, int]] = field(default_factory=list)
    
    # Performance
    max_concurrent_downloads: int = 5
    chunk_size: int = 256 * 1024  # 256KB
    
    # Timeouts (seconds)
    dht_timeout: float = 5.0
    transfer_timeout: float = 30.0
    discovery_timeout: float = 3.0
    
    # Logging
    log_level: str = 'INFO'
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables."""
        load_dotenv()
        
        config = cls()
        
        # Network
        config.host = os.getenv('P2P_HOST', config.host)
        config.dht_port = int(os.getenv('P2P_DHT_PORT', config.dht_port))
        config.transfer_port = int(os.getenv('P2P_TRANSFER_PORT', config.transfer_port))
        config.api_port = int(os.getenv('P2P_API_PORT', config.api_port))
        
        # Storage
        data_dir = os.getenv('P2P_DATA_DIR')
        if data_dir:
            config.data_dir = Path(data_dir)
        
        # Discovery
        config.auto_discover = os.getenv('P2P_AUTO_DISCOVER', 'true').lower() == 'true'
        
        bootstrap = os.getenv('P2P_BOOTSTRAP_NODES', '')
        if bootstrap:
            config.bootstrap_nodes = []
            for node in bootstrap.split(','):
                try:
                    host, port = node.strip().split(':')
                    config.bootstrap_nodes.append((host, int(port)))
                except ValueError:
                    pass
        
        # Performance
        config.max_concurrent_downloads = int(
            os.getenv('P2P_MAX_CONCURRENT', config.max_concurrent_downloads)
        )
        
        # Logging
        config.log_level = os.getenv('P2P_LOG_LEVEL', config.log_level)
        
        return config
    
    @classmethod
    def from_file(cls, path: Path) -> 'Config':
        """Load configuration from a JSON file."""
        if not path.exists():
            return cls()
        
        with open(path) as f:
            data = json.load(f)
        
        config = cls()
        
        # Network
        config.host = data.get('host', config.host)
        config.dht_port = data.get('dht_port', config.dht_port)
        config.transfer_port = data.get('transfer_port', config.transfer_port)
        config.api_port = data.get('api_port', config.api_port)
        
        # Storage
        if 'data_dir' in data:
            config.data_dir = Path(data['data_dir'])
        
        # Discovery
        config.auto_discover = data.get('auto_discover', config.auto_discover)
        config.bootstrap_nodes = [
            (node['host'], node['port'])
            for node in data.get('bootstrap_nodes', [])
        ]
        
        # Performance
        config.max_concurrent_downloads = data.get(
            'max_concurrent_downloads', config.max_concurrent_downloads
        )
        config.chunk_size = data.get('chunk_size', config.chunk_size)
        
        # Timeouts
        config.dht_timeout = data.get('dht_timeout', config.dht_timeout)
        config.transfer_timeout = data.get('transfer_timeout', config.transfer_timeout)
        
        # Logging
        config.log_level = data.get('log_level', config.log_level)
        
        return config
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'host': self.host,
            'dht_port': self.dht_port,
            'transfer_port': self.transfer_port,
            'api_port': self.api_port,
            'data_dir': str(self.data_dir),
            'auto_discover': self.auto_discover,
            'bootstrap_nodes': [
                {'host': h, 'port': p} for h, p in self.bootstrap_nodes
            ],
            'max_concurrent_downloads': self.max_concurrent_downloads,
            'chunk_size': self.chunk_size,
            'dht_timeout': self.dht_timeout,
            'transfer_timeout': self.transfer_timeout,
            'log_level': self.log_level,
        }
    
    def save(self, path: Path):
        """Save configuration to a JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Load configuration from file and environment.
    
    Environment variables override file settings.
    """
    # Start with defaults
    config = Config()
    
    # Load from file if provided
    if config_path and config_path.exists():
        config = Config.from_file(config_path)
    
    # Override with environment variables
    env_config = Config.from_env()
    
    # Merge (env takes precedence for non-default values)
    for key in ['host', 'dht_port', 'transfer_port', 'api_port', 
                'data_dir', 'auto_discover', 'log_level']:
        env_val = getattr(env_config, key)
        default_val = getattr(Config(), key)
        if env_val != default_val:
            setattr(config, key, env_val)
    
    # Bootstrap nodes are additive
    config.bootstrap_nodes.extend(env_config.bootstrap_nodes)
    
    return config


# Example config file template
EXAMPLE_CONFIG = """
{
  "host": "0.0.0.0",
  "dht_port": 8468,
  "transfer_port": 8469,
  "api_port": 8080,
  "data_dir": "./p2p_data",
  "auto_discover": true,
  "bootstrap_nodes": [
    {"host": "192.168.1.100", "port": 8468}
  ],
  "max_concurrent_downloads": 5,
  "chunk_size": 262144,
  "log_level": "INFO"
}
"""


if __name__ == "__main__":
    # Print example config
    print("Example configuration file (config.json):")
    print(EXAMPLE_CONFIG)



