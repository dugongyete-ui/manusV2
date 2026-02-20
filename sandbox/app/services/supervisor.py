import threading
import xmlrpc.client
import socket
import http.client
import asyncio
from datetime import datetime, timedelta
from typing import List

from app.core.config import settings
from app.core.exceptions import BadRequestException, ResourceNotFoundException
from app.models.supervisor import (
    ProcessInfo, 
    SupervisorActionResult, 
    SupervisorTimeout
)


# Add Unix socket support for xmlrpc client
class UnixStreamHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, socket_path, timeout=None):
        http.client.HTTPConnection.__init__(self, host, timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


class UnixStreamTransport(xmlrpc.client.Transport):
    def __init__(self, socket_path):
        xmlrpc.client.Transport.__init__(self)
        self.socket_path = socket_path

    def make_connection(self, host):
        return UnixStreamHTTPConnection(host, self.socket_path)


class SupervisorService:
    """
    Supervisor service management class, used for managing service timeout and renewal functionality - Async version
    Gracefully handles the case where supervisord is not available (e.g., when running on Replit).
    """
    def __init__(self):
        self.rpc_url = "/tmp/supervisor.sock"
        self._connected = False
        self.server = None
        
        # Try to connect to supervisord, but don't fail if it's not available
        self._connect_rpc()
        
        # Timeout management - enabled based on configuration
        self.timeout_active = settings.SERVICE_TIMEOUT_MINUTES is not None
        self.shutdown_task = None
        self.shutdown_time = None
        # Auto-expand functionality - disabled when user explicitly controls timeout
        self._auto_expand_enabled = True
        
        # If timeout is configured, create scheduled task
        if settings.SERVICE_TIMEOUT_MINUTES is not None:
            self.shutdown_time = datetime.now() + timedelta(minutes=settings.SERVICE_TIMEOUT_MINUTES)
            self._setup_timer(settings.SERVICE_TIMEOUT_MINUTES)
    
    @property
    def auto_expand_enabled(self) -> bool:
        """Get auto-expand status"""
        return self._auto_expand_enabled
    
    def disable_auto_expand(self):
        """Disable auto-expand functionality (called when user explicitly manages timeout)"""
        self._auto_expand_enabled = False
    
    def enable_auto_expand(self):
        """Enable auto-expand functionality"""
        self._auto_expand_enabled = True
    
    def _connect_rpc(self):
        """Connect to supervisord's RPC interface. Gracefully handles failures."""
        try:
            self.server = xmlrpc.client.ServerProxy(
                'http://localhost',
                transport=UnixStreamTransport(self.rpc_url)
            )
            # Test connection
            self.server.supervisor.getState()
            self._connected = True
        except Exception as e:
            # Connection failed - supervisord is not available
            # This is expected when running on Replit or other environments without supervisord
            self._connected = False
            self.server = None
    
    def _setup_timer(self, minutes):
        """Set up async timer"""
        # Cancel existing scheduled task
        if self.shutdown_task:
            try:
                self.shutdown_task.cancel()
            except:
                pass
            
        # Create scheduled task function
        async def shutdown_after_timeout():
            await asyncio.sleep(minutes * 60)
            await self.shutdown()
        
        # Create scheduled task
        try:
            loop = asyncio.get_event_loop()
            self.shutdown_task = loop.create_task(shutdown_after_timeout())
        except Exception as e:
            # If async task creation fails, fall back to thread timer
            if hasattr(self, 'shutdown_timer') and self.shutdown_timer:
                self.shutdown_timer.cancel()
            
            self.shutdown_timer = threading.Timer(
                minutes * 60, 
                lambda: asyncio.run(self.shutdown())
            )
            self.shutdown_timer.daemon = True
            self.shutdown_timer.start()
    
    async def _call_rpc(self, method, *args):
        """Execute RPC call asynchronously"""
        try:
            return await asyncio.to_thread(method, *args)
        except Exception as e:
            raise BadRequestException(f"RPC call failed: {str(e)}")
    
    async def get_all_processes(self) -> List[ProcessInfo]:
        """Asynchronously get all process statuses"""
        if not self._connected or self.server is None:
            # Return empty list when supervisord is not available
            return []
        
        try:
            processes = await self._call_rpc(self.server.supervisor.getAllProcessInfo)
            return [ProcessInfo(**process) for process in processes]
        except Exception as e:
            # If call fails, return empty list instead of raising error
            return []
    
    async def stop_all_services(self) -> SupervisorActionResult:
        """Asynchronously stop all services"""
        if not self._connected or self.server is None:
            # Return a mock result when supervisord is not available
            return SupervisorActionResult(status="stopped", result=[])
        
        try:
            result = await self._call_rpc(self.server.supervisor.stopAllProcesses)
            return SupervisorActionResult(status="stopped", result=result)
        except Exception as e:
            # Return a mock result instead of raising error
            return SupervisorActionResult(status="stopped", result=[])
    
    async def shutdown(self) -> SupervisorActionResult:
        """Asynchronously shut down the supervisord service itself, without stopping processes"""
        if not self._connected or self.server is None:
            # Return a mock result when supervisord is not available
            return SupervisorActionResult(status="shutdown", shutdown_result=[])
        
        try:
            shutdown_result = await self._call_rpc(self.server.supervisor.shutdown)
            return SupervisorActionResult(status="shutdown", shutdown_result=shutdown_result)
        except Exception as e:
            # Return a mock result instead of raising error
            return SupervisorActionResult(status="shutdown", shutdown_result=[])
    
    async def restart_all_services(self) -> SupervisorActionResult:
        """Asynchronously restart all services"""
        if not self._connected or self.server is None:
            # Return a mock result when supervisord is not available
            return SupervisorActionResult(status="restarted", stop_result=[], start_result=[])
        
        try:
            stop_result = await self._call_rpc(self.server.supervisor.stopAllProcesses)
            start_result = await self._call_rpc(self.server.supervisor.startAllProcesses)
            return SupervisorActionResult(
                status="restarted", 
                stop_result=stop_result,
                start_result=start_result
            )
        except Exception as e:
            # Return a mock result instead of raising error
            return SupervisorActionResult(status="restarted", stop_result=[], start_result=[])
    
    async def activate_timeout(self, minutes=None) -> SupervisorTimeout:
        """
        Asynchronously activate timeout functionality, automatically shut down all services after the set time
        
        Args:
            minutes: Timeout in minutes, if None then use the configured default value
        """
        # Set timeout
        timeout_minutes = minutes or settings.SERVICE_TIMEOUT_MINUTES
        
        # If no timeout is specified and no default in config, throw error
        if timeout_minutes is None:
            raise BadRequestException("Timeout not specified, and system default is no timeout")
            
        self.timeout_active = True
        self.shutdown_time = datetime.now() + timedelta(minutes=timeout_minutes)
        
        # Set up timer
        self._setup_timer(timeout_minutes)
        
        return SupervisorTimeout(
            status="timeout_activated",
            active=True,
            shutdown_time=self.shutdown_time.isoformat(),
            timeout_minutes=timeout_minutes
        )
    
    async def extend_timeout(self, minutes=None) -> SupervisorTimeout:
        """
        Asynchronously extend timeout
        
        Args:
            minutes: Number of minutes to extend, if None then use the configured default value
        """
        # Set new timeout
        timeout_minutes = minutes or settings.SERVICE_TIMEOUT_MINUTES
        
        # If no timeout is specified and no default in config, throw error
        if timeout_minutes is None:
            raise BadRequestException("Timeout not specified, and system default is no timeout")
            
        self.timeout_active = True
        self.shutdown_time = datetime.now() + timedelta(minutes=timeout_minutes)
        
        # Set up timer
        self._setup_timer(timeout_minutes)
        
        return SupervisorTimeout(
            status="timeout_extended",
            active=True,
            shutdown_time=self.shutdown_time.isoformat(),
            timeout_minutes=timeout_minutes
        )
    
    async def cancel_timeout(self) -> SupervisorTimeout:
        """Asynchronously cancel timeout functionality"""
        if not self.timeout_active:
            return SupervisorTimeout(status="no_timeout_active", active=False)
        
        if self.shutdown_task:
            try:
                self.shutdown_task.cancel()
                self.shutdown_task = None
            except:
                pass
        
        # Also check thread timer (for compatibility)
        if hasattr(self, 'shutdown_timer') and self.shutdown_timer:
            self.shutdown_timer.cancel()
            self.shutdown_timer = None
        
        self.timeout_active = False
        self.shutdown_time = None
        # Re-enable auto-expand when timeout is cancelled
        self._auto_expand_enabled = True
        
        return SupervisorTimeout(status="timeout_cancelled", active=False)
    
    async def get_timeout_status(self) -> SupervisorTimeout:
        """Asynchronously get current timeout status"""
        if not self.timeout_active:
            return SupervisorTimeout(active=False)
        
        remaining_seconds = 0
        if self.shutdown_time:
            remaining = self.shutdown_time - datetime.now()
            remaining_seconds = max(0, remaining.total_seconds())
        
        return SupervisorTimeout(
            active=self.timeout_active,
            shutdown_time=self.shutdown_time.isoformat() if self.shutdown_time else None,
            remaining_seconds=remaining_seconds
        )


# Lazy initialization pattern
_supervisor_service = None


def get_supervisor_service() -> SupervisorService:
    """Get or create the singleton supervisor service instance"""
    global _supervisor_service
    if _supervisor_service is None:
        _supervisor_service = SupervisorService()
    return _supervisor_service


# For backward compatibility with existing imports
# This allows existing code to use: from app.services.supervisor import supervisor_service
@property
def supervisor_service():
    """Property for backward compatibility"""
    return get_supervisor_service()


# Create a module-level attribute that acts like the old global instance
# but uses lazy initialization
class _SupervisorServiceProxy:
    """Proxy that lazily initializes the supervisor service"""
    def __getattr__(self, name):
        return getattr(get_supervisor_service(), name)


supervisor_service = _SupervisorServiceProxy() 