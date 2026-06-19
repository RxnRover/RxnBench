"""
client for the Moonraker API on the SV08.

Author: John Brittain
Date: Jun 17 2026
"""

class CrowsnestClient:
    """Client for communicating with Crowsnest, a camera server hosted by SV08.
    
    This is a very basic implementation for demonstration purposes. In a real implementation, you would want to add error handling, support for multiple cameras, etc.
    """
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
    