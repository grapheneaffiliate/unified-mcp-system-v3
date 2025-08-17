"""
Sandbox security for filesystem and network access control.
"""

import os
import subprocess
import urllib.parse
from pathlib import Path

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("security.sandbox")


class SandboxViolationError(Exception):
    """Raised when a sandbox security violation is detected."""
    pass


class SandboxManager:
    """Manages filesystem and network security constraints."""

    def __init__(self):
        self.allowed_paths: set[Path] = set()
        self.allowed_domains: set[str] = set(settings.allowed_domains)
        self.setup_allowed_paths()

    def setup_allowed_paths(self):
        """Setup allowed filesystem paths."""
        # Add configured sandbox directory
        self.allowed_paths.add(settings.sandbox_dir.resolve())

        # Add Jupyter notebooks directory
        self.allowed_paths.add(settings.jupyter_notebooks_dir.resolve())

        # Add temporary directories (for Docker operations)
        import tempfile
        self.allowed_paths.add(Path(tempfile.gettempdir()).resolve())

        logger.info(
            "Sandbox paths configured",
            allowed_paths=[str(p) for p in self.allowed_paths],
            allowed_domains=list(self.allowed_domains)
        )

    def validate_file_path(self, file_path: str | Path) -> Path:
        """Validate and resolve file path within sandbox constraints."""
        if not settings.sandbox_enabled:
            return Path(file_path).resolve()

        # Convert to Path object and resolve
        path = Path(file_path).resolve()

        # Check if path is within any allowed directory
        for allowed_path in self.allowed_paths:
            try:
                path.relative_to(allowed_path)
                logger.debug("File path validated", path=str(path), allowed_root=str(allowed_path))
                return path
            except ValueError:
                continue

        # If we get here, path is not within any allowed directory
        logger.error(
            "Sandbox violation: file path outside allowed directories",
            path=str(path),
            allowed_paths=[str(p) for p in self.allowed_paths]
        )
        raise SandboxViolationError(
            f"File path '{path}' is outside allowed sandbox directories"
        )

    def validate_url(self, url: str) -> str:
        """Validate URL against allowed domains."""
        if not settings.network_restrictions:
            return url

        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()

            # Remove port if present
            if ':' in domain:
                domain = domain.split(':')[0]

            # Check if domain or any parent domain is allowed
            for allowed_domain in self.allowed_domains:
                if domain == allowed_domain or domain.endswith(f'.{allowed_domain}'):
                    logger.debug("URL validated", url=url, domain=domain)
                    return url

            logger.error(
                "Sandbox violation: URL domain not allowed",
                url=url,
                domain=domain,
                allowed_domains=list(self.allowed_domains)
            )
            raise SandboxViolationError(
                f"URL domain '{domain}' is not in allowed domains list"
            )

        except Exception as e:
            if isinstance(e, SandboxViolationError):
                raise
            logger.error("Error validating URL", url=url, error=str(e))
            raise SandboxViolationError(f"Invalid URL format: {url}") from e

    def create_secure_subprocess(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: int = 30,
        **kwargs
    ) -> subprocess.Popen:
        """Create a subprocess with security constraints."""
        if not settings.sandbox_enabled:
            return subprocess.Popen(command, cwd=cwd, **kwargs)

        # Validate working directory
        if cwd:
            validated_cwd = self.validate_file_path(cwd)
            cwd = str(validated_cwd)

        # Security constraints for subprocess
        security_kwargs = {
            'cwd': cwd,
            'timeout': timeout,
            'env': self._get_secure_environment(),
            **kwargs
        }

        # On Unix systems, we can add additional security
        if os.name == 'posix':
            # Prevent new privileges
            security_kwargs['preexec_fn'] = os.setsid

        logger.debug(
            "Creating secure subprocess",
            command=command,
            cwd=cwd,
            timeout=timeout
        )

        return subprocess.Popen(command, **security_kwargs)

    def _get_secure_environment(self) -> dict:
        """Get a secure environment for subprocess execution."""
        # Start with minimal environment
        secure_env = {
            'PATH': os.environ.get('PATH', ''),
            'HOME': os.environ.get('HOME', ''),
            'USER': os.environ.get('USER', ''),
            'LANG': os.environ.get('LANG', 'en_US.UTF-8'),
            'LC_ALL': os.environ.get('LC_ALL', 'en_US.UTF-8'),
        }

        # Add specific environment variables needed for tools
        allowed_env_vars = [
            'OPENAI_API_KEY',
            'GOOGLE_API_KEY',
            'COMPOSIO_API_KEY',
            'PYTHONPATH',
            'PYTHONIOENCODING',
        ]

        for var in allowed_env_vars:
            if var in os.environ:
                secure_env[var] = os.environ[var]

        return secure_env

    def add_allowed_path(self, path: str | Path):
        """Add a new allowed path to the sandbox."""
        resolved_path = Path(path).resolve()
        self.allowed_paths.add(resolved_path)
        logger.info("Added allowed path to sandbox", path=str(resolved_path))

    def add_allowed_domain(self, domain: str):
        """Add a new allowed domain for network access."""
        domain = domain.lower()
        self.allowed_domains.add(domain)
        logger.info("Added allowed domain to sandbox", domain=domain)

    def remove_allowed_path(self, path: str | Path):
        """Remove an allowed path from the sandbox."""
        resolved_path = Path(path).resolve()
        self.allowed_paths.discard(resolved_path)
        logger.info("Removed allowed path from sandbox", path=str(resolved_path))

    def remove_allowed_domain(self, domain: str):
        """Remove an allowed domain from network access."""
        domain = domain.lower()
        self.allowed_domains.discard(domain)
        logger.info("Removed allowed domain from sandbox", domain=domain)

    def get_sandbox_info(self) -> dict:
        """Get current sandbox configuration."""
        return {
            "enabled": settings.sandbox_enabled,
            "network_restrictions": settings.network_restrictions,
            "allowed_paths": [str(p) for p in self.allowed_paths],
            "allowed_domains": list(self.allowed_domains),
        }


# Global sandbox manager instance
sandbox_manager = SandboxManager()


def get_sandbox_manager() -> SandboxManager:
    """Get the global sandbox manager instance."""
    return sandbox_manager


def validate_file_access(file_path: str | Path) -> Path:
    """Validate file access through sandbox manager."""
    return sandbox_manager.validate_file_path(file_path)


def validate_network_access(url: str) -> str:
    """Validate network access through sandbox manager."""
    return sandbox_manager.validate_url(url)


def secure_subprocess(command: list[str], **kwargs) -> subprocess.Popen:
    """Create a secure subprocess through sandbox manager."""
    return sandbox_manager.create_secure_subprocess(command, **kwargs)


class SandboxDecorator:
    """Decorator for automatic sandbox validation."""

    def __init__(self, validate_files: bool = True, validate_urls: bool = True):
        self.validate_files = validate_files
        self.validate_urls = validate_urls

    def __call__(self, func):
        async def async_wrapper(*args, **kwargs):
            if self.validate_files:
                # Look for file path parameters
                for key, value in kwargs.items():
                    if 'path' in key.lower() or 'file' in key.lower():
                        if isinstance(value, str | Path):
                            kwargs[key] = validate_file_access(value)

            if self.validate_urls:
                # Look for URL parameters
                for key, value in kwargs.items():
                    if 'url' in key.lower():
                        if isinstance(value, str) and value.startswith(('http://', 'https://')):
                            kwargs[key] = validate_network_access(value)

            return await func(*args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            if self.validate_files:
                # Look for file path parameters
                for key, value in kwargs.items():
                    if 'path' in key.lower() or 'file' in key.lower():
                        if isinstance(value, str | Path):
                            kwargs[key] = validate_file_access(value)

            if self.validate_urls:
                # Look for URL parameters
                for key, value in kwargs.items():
                    if 'url' in key.lower():
                        if isinstance(value, str) and value.startswith(('http://', 'https://')):
                            kwargs[key] = validate_network_access(value)

            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper


def sandbox_validate(validate_files: bool = True, validate_urls: bool = True):
    """Decorator for sandbox validation."""
    return SandboxDecorator(validate_files, validate_urls)
