# core/stream_parser.py
import re
import json
from typing import Generator, AsyncGenerator
from core.models.messages import AuraMessage, MessageType


class LLMStreamParser:
    """
    Parses LLM streaming responses and extracts structured messages from tags
    like <thought>, <response>, and [TOOL_CALL].
    """

    def __init__(self):
        self.buffer = ""

    def parse_chunk(self, chunk: str) -> Generator[AuraMessage, None, None]:
        """
        Parses a streaming chunk and yields AuraMessage objects for any complete sections found.
        """
        self.buffer += chunk

        # First, try to handle complete JSON blocks from architect agents
        if self.buffer.strip().startswith('{'):
            try:
                # Attempt to parse the entire buffer as a JSON object
                parsed_json = json.loads(self.buffer)
                # If successful, we have a complete plan. Yield it and clear the buffer.
                yield AuraMessage(type=MessageType.AGENT_PLAN_JSON, content=self.buffer)
                self.buffer = ""
                return
            except json.JSONDecodeError:
                # The buffer is not a complete JSON object yet, so continue buffering.
                pass

        # If not a JSON block, process for other tags
        while True:
            matches = []
            thought_match = re.search(r'<thought>(.*?)</thought>', self.buffer, re.DOTALL)
            if thought_match:
                matches.append({'type': 'thought', 'match': thought_match})

            response_match = re.search(r'<response>(.*?)</response>', self.buffer, re.DOTALL)
            if response_match:
                matches.append({'type': 'response', 'match': response_match})

            tool_match = re.search(r'\[TOOL_CALL\](.*?)\[/TOOL_CALL\]', self.buffer, re.DOTALL)
            if tool_match:
                matches.append({'type': 'tool', 'match': tool_match})

            if not matches:
                break

            first_match_info = min(matches, key=lambda m: m['match'].start())
            match_obj = first_match_info['match']
            match_type = first_match_info['type']

            pre_match_content = self.buffer[:match_obj.start()].strip()
            if pre_match_content:
                yield AuraMessage.agent_response(pre_match_content)

            content = match_obj.group(1).strip()
            if content:
                if match_type == 'thought':
                    yield AuraMessage.agent_thought(content)
                elif match_type == 'response':
                    yield AuraMessage.agent_response(content)
                elif match_type == 'tool':
                    yield AuraMessage.tool_call(content)

            self.buffer = self.buffer[match_obj.end():]

    def finalize(self) -> Generator[AuraMessage, None, None]:
        """
        Process any remaining content in the buffer when streaming is complete.
        """
        content = self.buffer.strip()
        if content:
            # If there's remaining content that isn't a JSON plan, treat as a final response.
            if not content.startswith('{'):
                yield AuraMessage.agent_response(content)
        self.buffer = ""


async def parse_llm_stream_async(stream_chunks: AsyncGenerator[str, None]) -> AsyncGenerator[AuraMessage, None]:
    parser = LLMStreamParser()
    try:
        async for chunk in stream_chunks:
            for message in parser.parse_chunk(chunk):
                yield message
    finally:
        for message in parser.finalize():
            yield message
