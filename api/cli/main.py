"""Karma CLI — search and retrieve Claude Code session context."""
import click

from .search import search
from .sessions import sessions


@click.group()
def cli():
    """Karma — Claude Code session search and context retrieval."""
    pass


cli.add_command(search)
cli.add_command(sessions)
