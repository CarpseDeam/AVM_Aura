# gui/utils.py
"""
Contains utility functions for the GUI, such as printing banners or other startup info.
"""
import logging

logger = logging.getLogger(__name__)

def get_aura_banner() -> str:
    """
    Returns a cool ASCII art banner for Aura as a string.
    """

    banner = """
    █████╗ ██╗   ██╗██████╗  █████╗ 
   ██╔══██╗██║   ██║██╔══██╗██╔══██╗
   ███████║██║   ██║██████╔╝███████║
   ██╔══██║██║   ██║██╔══██╗██╔══██║
   ██║  ██║╚██████╔╝██║  ██║██║  ██║
   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
   A U T O N O M O U S   V I R T U A L   M A C H I N E
    """
    logger.info("Aura banner string requested.")
    return banner