# core/stream_parser.py
import re
from typing import Generator, AsyncGenerator
from core.models.messages import AuraMessage, MessageType


class LLMStreamParser:
    """
    Parses LLM streaming responses and extracts structured messages from tags
    like <thought>, <response>, and [TOOL_CALL].
    Handles partial chunks and maintains state across streaming calls.
    """

    def __init__(self):
        self.buffer = ""

    def parse_chunk(self, chunk: str) -> Generator[AuraMessage, None, None]:
        """
        Parses a streaming chunk and yields AuraMessage objects for any complete sections found.
        """
        self.buffer += chunk

        while True:
            matches = []
            # Find the first complete match for each tag type
            thought_match = re.search(r'<thought>(.*?)</thought>', self.buffer, re.DOTALL)
            if thought_match:
                matches.append({'type': 'thought', 'match': thought_match})

            response_match = re.search(r'<response>(.*?)</response>', self.buffer, re.DOTALL)
            if response_match:
                matches.append({'type': 'response', 'match': response_match})

            tool_match = re.search(r'\\\[TOOL_CALL\\\](.*?)\\\[/TOOL_CALL\\\]', self.buffer, re.DOTALL)
            if tool_match:
                matches.append({'type': 'tool', 'match': tool_match})

            if not matches:
                break  # No complete blocks found, wait for more data

            # Find the match that appears earliest in the buffer
            first_match_info = min(matches, key=lambda m: m['match'].start())

            match_obj = first_match_info['match']
            match_type = first_match_info['type']

            # Check if there is any text before this first match
            pre_match_content = self.buffer[:match_obj.start()].strip()
            if pre_match_content:
                # This is untagged content. Could be a final JSON object or conversational text.
                # We'll yield it based on whether it looks like JSON.
                if pre_match_content.startswith('{') and pre_match_content.endswith('}'):
                    yield AuraMessage.tool_call(pre_match_content)
                else:
                    yield AuraMessage.agent_response(pre_match_content)

            # Process the matched block
            content = match_obj.group(1).strip()
            if content:
                if match_type == 'thought':
                    yield AuraMessage.agent_thought(content)
                elif match_type == 'response':
                    yield AuraMessage.agent_response(content)
                elif match_type == 'tool':
                    yield AuraMessage.tool_call(content)

            # Update buffer to remove everything up to the end of the processed match
            self.buffer = self.buffer[match_obj.end():]
            # Continue loop to process rest of buffer

    def finalize(self) -> Generator[AuraMessage, None, None]:
        """
        Process any remaining content in the buffer when streaming is complete.
        """
        content = self.buffer.strip()
        if content:
            # Check if the remaining content is a JSON object
            if content.startswith('{') and content.endswith('}'):
                yield AuraMessage.tool_call(content)
            else:
                # Otherwise, it's a final conversational response
                yield AuraMessage.agent_response(content)
        self.buffer = ""


async def parse_llm_stream_async(stream_chunks: AsyncGenerator[str, None]) -> AsyncGenerator[AuraMessage, None]:
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


def parse_llm_stream(stream_chunks: Generator[str, None, None]) -> Generator[AuraMessage, None, None]:
    """
    Convenience function to parse an entire LLM stream into AuraMessage objects.

    Args:
        stream_chunks: Generator yielding string chunks from LLM

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

