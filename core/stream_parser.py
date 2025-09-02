# core/stream_parser.py
import re
from typing import Generator, Tuple, Optional
from core.models.messages import AuraMessage, MessageType


class LLMStreamParser:
    """
    Parses LLM streaming responses and extracts structured messages from thought/response tags.
    Handles partial chunks and maintains state across streaming calls.
    """
    
    def __init__(self):
        self.buffer = ""
        self.current_section = None
        self.sections = {}
    
    def parse_chunk(self, chunk: str) -> Generator[AuraMessage, None, None]:
        """
        Parse a streaming chunk and yield AuraMessage objects.
        Handles partial tags across chunk boundaries.
        """
        self.buffer += chunk
        
        # Look for complete sections
        while True:
            # Try to find opening tag
            thought_match = re.search(r'<thought>(.*?)(?=</thought>|<response>|<tool>|$)', self.buffer, re.DOTALL)
            response_match = re.search(r'<response>(.*?)(?=</response>|<thought>|<tool>|$)', self.buffer, re.DOTALL)
            
            # Check for complete thought section
            if thought_match and '</thought>' in self.buffer:
                thought_end = self.buffer.find('</thought>', thought_match.start())
                if thought_end != -1:
                    content = self.buffer[thought_match.start()+9:thought_end].strip()
                    if content:
                        yield AuraMessage.agent_thought(content)
                    self.buffer = self.buffer[thought_end+10:]  # Remove processed content
                    continue
            
            # Check for complete response section
            if response_match and '</response>' in self.buffer:
                response_end = self.buffer.find('</response>', response_match.start())
                if response_end != -1:
                    content = self.buffer[response_match.start()+10:response_end].strip()
                    if content:
                        yield AuraMessage.agent_response(content)
                    self.buffer = self.buffer[response_end+11:]  # Remove processed content
                    continue
            
            # Look for tool calls (existing format)
            tool_match = re.search(r'\[TOOL_CALL\](.*?)\[/TOOL_CALL\]', self.buffer, re.DOTALL)
            if tool_match:
                tool_content = tool_match.group(1).strip()
                if tool_content:
                    # Try to parse tool name from JSON
                    try:
                        import json
                        tool_data = json.loads(tool_content)
                        tool_name = tool_data.get('tool_name', 'unknown')
                        yield AuraMessage.tool_call(f"Executing {tool_name}", tool_name=tool_name)
                    except:
                        yield AuraMessage.tool_call(f"Executing tool: {tool_content[:50]}...")
                
                # Remove processed content
                self.buffer = self.buffer[:tool_match.start()] + self.buffer[tool_match.end():]
                continue
            
            # No more complete sections found
            break
    
    def finalize(self) -> Generator[AuraMessage, None, None]:
        """
        Process any remaining content in the buffer when streaming is complete.
        Handles cases where tags might be incomplete or missing.
        """
        if self.buffer.strip():
            # If there's remaining content without proper tags, treat as agent response
            content = self.buffer.strip()
            
            # Remove any partial opening tags
            content = re.sub(r'<(?:thought|response)>.*$', '', content, flags=re.DOTALL)
            
            if content:
                yield AuraMessage.agent_response(content)
        
        # Clear buffer
        self.buffer = ""


def parse_llm_stream(stream_chunks):
    """
    Convenience function to parse an entire LLM stream into AuraMessage objects.
    
    Args:
        stream_chunks: Generator or AsyncGenerator yielding string chunks from LLM
        
    Yields:
        AuraMessage objects extracted from the stream
    """
    parser = LLMStreamParser()
    
    try:
        for chunk in stream_chunks:
            yield from parser.parse_chunk(chunk)
    finally:
        # Process any remaining content
        yield from parser.finalize()


async def parse_llm_stream_async(stream_chunks):
    """
    Async version for parsing async generators from LLM streams.
    
    Args:
        stream_chunks: AsyncGenerator yielding string chunks from LLM
        
    Yields:
        AuraMessage objects extracted from the stream
    """
    parser = LLMStreamParser()
    
    try:
        async for chunk in stream_chunks:
            for message in parser.parse_chunk(chunk):
                yield message
    finally:
        # Process any remaining content
        for message in parser.finalize():
            yield message