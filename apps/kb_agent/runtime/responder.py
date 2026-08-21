from __future__ import annotations

from google import genai

from .pack_loader import KnowledgePack


class GeminiResponder:
    def __init__(self, pack: KnowledgePack):
        self.pack = pack
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client()
        return self._client

    def generate(self, prompt: str) -> str:
        model = self.pack.responder.get('model', 'gemini-2.5-flash')
        response = self.client.models.generate_content(model=model, contents=prompt)
        return (response.text or '').strip()
