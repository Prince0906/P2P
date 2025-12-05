#!/usr/bin/env python3
"""
P2P File Sharing CLI

Command-line interface for the DHT-based P2P file sharing system.

Usage:
    python cli.py start              # Start a node
    python cli.py share FILE         # Share a file
    python cli.py download HASH      # Download a file
    python cli.py list               # List shared files
    python cli.py peers              # List discovered peers
    python cli.py status             # Show node status
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.logging import RichHandler

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.node import P2PNode, NodeConfig
from src.file import FileManifest

console = Console()


def setup_logging(verbose: bool = False):
    """Configure logging with rich output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=False, show_path=False)]
    )


# Global node reference for commands that need it
_node: Optional[P2PNode] = None


@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
@click.option('--data-dir', default='./p2p_data', help='Data directory')
@click.option('--dht-port', default=8468, help='DHT UDP port')
@click.option('--transfer-port', default=8469, help='File transfer TCP port')
@click.pass_context
def cli(ctx, verbose, data_dir, dht_port, transfer_port):
    """P2P File Sharing System - DHT-based decentralized file sharing."""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj['config'] = NodeConfig(
        data_dir=Path(data_dir),
        dht_port=dht_port,
        transfer_port=transfer_port,
    )


@cli.command()
@click.option('--api-port', default=8080, help='REST API port')
@click.option('--no-api', is_flag=True, help='Disable REST API')
@click.option('--bootstrap', multiple=True, help='Bootstrap node (host:port)')
@click.pass_context
def start(ctx, api_port, no_api, bootstrap):
    """Start a P2P node."""
    config = ctx.obj['config']
    
    # Parse bootstrap nodes
    if bootstrap:
        config.bootstrap_nodes = []
        for node in bootstrap:
            try:
                host, port = node.split(':')
                config.bootstrap_nodes.append((host, int(port)))
            except ValueError:
                console.print(f"[red]Invalid bootstrap format: {node} (use host:port)[/red]")
                return
    
    async def run():
        node = P2PNode(config)
        
        try:
            await node.start()
            
            # Display info
            console.print(Panel.fit(
                f"[bold green]P2P Node Started[/bold green]\n\n"
                f"Node ID: [cyan]{node.node_id_hex[:32]}...[/cyan]\n"
                f"DHT Port: [yellow]{config.dht_port}[/yellow]\n"
                f"Transfer Port: [yellow]{config.transfer_port}[/yellow]\n"
                f"Data Dir: [blue]{config.data_dir}[/blue]",
                title="Node Info"
            ))
            
            if not no_api:
                console.print(f"\n[dim]REST API available at http://localhost:{api_port}[/dim]")
                console.print("[dim]API docs at http://localhost:{api_port}/docs[/dim]\n")
                
                from src.api import run_api_server
                await run_api_server(node, port=api_port)
            else:
                console.print("\n[dim]Press Ctrl+C to stop[/dim]\n")
                while True:
                    await asyncio.sleep(1)
                    
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
        finally:
            await node.stop()
            console.print("[green]Node stopped[/green]")
    
    asyncio.run(run())


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--description', '-d', default='', help='File description')
@click.pass_context
def share(ctx, file_path, description):
    """Share a file with the network."""
    config = ctx.obj['config']
    file_path = Path(file_path)
    
    async def run():
        node = P2PNode(config)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Starting node...", total=None)
            await node.start()
            
            progress.update(task, description="Sharing file...")
            manifest = await node.share(file_path, description)
            
            progress.update(task, description="Done!")
        
        # Display result
        console.print(Panel.fit(
            f"[bold green]File Shared Successfully[/bold green]\n\n"
            f"Name: [cyan]{manifest.name}[/cyan]\n"
            f"Size: [yellow]{manifest.size:,} bytes[/yellow]\n"
            f"Chunks: [yellow]{manifest.chunk_count}[/yellow]\n\n"
            f"[bold]Info Hash (share this):[/bold]\n"
            f"[green]{manifest.info_hash}[/green]",
            title="Shared File"
        ))
        
        await node.stop()
    
    asyncio.run(run())


@cli.command()
@click.argument('info_hash')
@click.option('--output', '-o', type=click.Path(), help='Output path')
@click.pass_context
def download(ctx, info_hash, output):
    """Download a file from the network."""
    config = ctx.obj['config']
    output_path = Path(output) if output else None
    
    async def run():
        node = P2PNode(config)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("Starting node...", total=100)
            await node.start()
            
            progress.update(task, description="Finding peers...")
            
            # Progress callback
            def update_progress(p):
                progress.update(
                    task, 
                    completed=p.progress_percent,
                    description=f"Downloading... ({p.downloaded_chunks}/{p.total_chunks} chunks)"
                )
            
            result = await node.download(info_hash, output_path, update_progress)
            
            if result:
                progress.update(task, completed=100, description="Done!")
                console.print(f"\n[green]✓ Downloaded to: {result}[/green]")
            else:
                console.print("\n[red]✗ Download failed[/red]")
        
        await node.stop()
    
    asyncio.run(run())


@cli.command('list')
@click.pass_context
def list_files(ctx):
    """List shared files."""
    config = ctx.obj['config']
    
    async def run():
        node = P2PNode(config)
        await node.start()
        
        manifests = await node.list_shared_files()
        
        if not manifests:
            console.print("[yellow]No shared files[/yellow]")
        else:
            table = Table(title="Shared Files")
            table.add_column("Name", style="cyan")
            table.add_column("Size", justify="right", style="yellow")
            table.add_column("Chunks", justify="right")
            table.add_column("Info Hash", style="green")
            
            for m in manifests:
                size_str = format_size(m.size)
                table.add_row(
                    m.name,
                    size_str,
                    str(m.chunk_count),
                    m.info_hash[:16] + "..."
                )
            
            console.print(table)
        
        await node.stop()
    
    asyncio.run(run())


@cli.command()
@click.pass_context
def peers(ctx):
    """List discovered peers."""
    config = ctx.obj['config']
    
    async def run():
        node = P2PNode(config)
        
        console.print("[dim]Discovering peers...[/dim]")
        await node.start()
        await asyncio.sleep(3)  # Wait for discovery
        
        discovered = node.get_peers()
        dht_nodes = node.dht.routing_table.get_all_nodes()
        
        if not discovered and not dht_nodes:
            console.print("[yellow]No peers found[/yellow]")
        else:
            if discovered:
                table = Table(title="Discovered Peers (LAN)")
                table.add_column("Node ID", style="cyan")
                table.add_column("IP", style="yellow")
                table.add_column("DHT Port")
                table.add_column("Transfer Port")
                
                for p in discovered:
                    table.add_row(
                        p.node_id[:16] + "...",
                        p.ip,
                        str(p.dht_port),
                        str(p.transfer_port)
                    )
                
                console.print(table)
            
            if dht_nodes:
                table = Table(title="DHT Routing Table")
                table.add_column("Node ID", style="cyan")
                table.add_column("Address", style="yellow")
                
                for n in dht_nodes[:20]:
                    table.add_row(
                        n.node_id.hex()[:16] + "...",
                        f"{n.ip}:{n.port}"
                    )
                
                if len(dht_nodes) > 20:
                    console.print(f"[dim]... and {len(dht_nodes) - 20} more[/dim]")
                
                console.print(table)
        
        await node.stop()
    
    asyncio.run(run())


@cli.command()
@click.pass_context
def status(ctx):
    """Show node status."""
    config = ctx.obj['config']
    
    async def run():
        node = P2PNode(config)
        await node.start()
        
        stats = node.get_full_stats()
        storage = await node.get_storage_stats()
        
        console.print(Panel.fit(
            f"[bold]Node Status[/bold]\n\n"
            f"Node ID: [cyan]{stats['node_id'][:32]}...[/cyan]\n"
            f"Running: [green]{'Yes' if stats['running'] else 'No'}[/green]\n\n"
            f"[bold]DHT[/bold]\n"
            f"  Nodes in routing table: [yellow]{stats['dht']['routing_table']['total_nodes']}[/yellow]\n"
            f"  Stored values: [yellow]{stats['dht']['stored_values']}[/yellow]\n"
            f"  Tracked files: [yellow]{stats['dht']['tracked_files']}[/yellow]\n\n"
            f"[bold]Discovery[/bold]\n"
            f"  Discovered peers: [yellow]{stats['discovery']['total_peers']}[/yellow]\n"
            f"  mDNS available: [{'green' if stats['discovery']['mdns_available'] else 'red'}]"
            f"{'Yes' if stats['discovery']['mdns_available'] else 'No'}[/]\n\n"
            f"[bold]Storage[/bold]\n"
            f"  Chunks: [yellow]{storage['chunks']}[/yellow]\n"
            f"  Size: [yellow]{format_size(storage['bytes'])}[/yellow]\n"
            f"  Manifests: [yellow]{storage['manifests']}[/yellow]",
            title="P2P Node Status"
        ))
        
        await node.stop()
    
    asyncio.run(run())


def format_size(bytes_count: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f} PB"


if __name__ == '__main__':
    cli()



