# core/stream_parser.py
import re
import json
from typing import Generator, AsyncGenerator
from core.models.messages import AuraMessage, MessageType


class LLMStreamParser:
    """
    Parses LLM streaming responses. This parser is designed to aggressively find
    and process a single, primary JSON object (the plan) and discard any
    surrounding conversational text to prevent it from leaking to the UI.
    """

    def __init__(self):
        self.buffer = ""
        self.plan_processed = False

    def parse_chunk(self, chunk: str) -> Generator[AuraMessage, None, None]:
        """
        Parses a streaming chunk. Once a JSON plan is found and processed,
        it will stop processing to prevent any other content from being displayed.
        """
        if self.plan_processed:
            return # A plan has been found and handled; do nothing else.

        self.buffer += chunk

        # Aggressively search for a complete JSON object in the buffer.
        json_match = re.search(r'(\{.*?\})', self.buffer, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            try:
                # Validate that the matched string is a complete JSON object.
                json.loads(json_str)

                # It's a valid plan. Yield it for backend processing.
                yield AuraMessage(type=MessageType.AGENT_PLAN_JSON, content=json_str)

                # Mark the plan as processed and clear the buffer.
                # This effectively stops any further parsing of this stream.
                self.plan_processed = True
                self.buffer = ""
                return

            except json.JSONDecodeError:
                # The buffer contains something that looks like JSON, but it's not
                # complete yet. Continue buffering to get the full object.
                pass

        # This part of the logic will only run if a JSON plan has not yet been found.
        # It handles simple, non-plan conversational responses.
        while True:
            tag_match = re.search(r'<response>(.*?)</response>', self.buffer, re.DOTALL)
            if not tag_match:
                break

            content = tag_match.group(1).strip()
            if content:
                yield AuraMessage.agent_response(content)

            # Remove the processed tag and all content before it.
            self.buffer = self.buffer[tag_match.end():]

    def finalize(self) -> Generator[AuraMessage, None, None]:
        """
        Finalizes the stream. This is intentionally left blank to prevent any
        unprocessed buffer content (like partial thoughts or pre-JSON text)
        from being accidentally displayed.
        """
        self.buffer = ""
        yield from ()


async def parse_llm_stream_async(stream_chunks: AsyncGenerator[str, None]) -> AsyncGenerator[AuraMessage, None]:
    """Asynchronously parses a stream of LLM chunks into AuraMessages."""
    parser = LLMStreamParser()
    try:
        async for chunk in stream_chunks:
            for message in parser.parse_chunk(chunk):
                yield message
    finally:
        for message in parser.finalize():
            yield message
