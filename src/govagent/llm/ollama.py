import httpx

from govagent.llm.base import BaseLLMClient, LLMRequest, LLMResponse


class OllamaClient(BaseLLMClient):
    """
    Local Small Language Model (SLM) client interface. 
    Prioritizes corporate data privacy and zero cloud token leakage.
    """
    async def generate(self, request: LLMRequest) -> LLMResponse:
        base_url = self.config.get("base_url", "http://localhost:11434")
        model = self.config.get("model", "llama3")
        
        payload = {
            "model": model,
            "prompt": request.prompt,
            "options": {
                "temperature": request.temperature
            },
            "stream": False
        }
        if request.system_instruction:
            payload["system"] = request.system_instruction

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{base_url}/api/generate", json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"Ollama local inference failed: {response.text}")
            
            data = response.json()
            
            # Note: Basic Ollama generation API mapping. 
            # For structured tool-calling support, we will parse its /api/chat endpoint matrix.
            return LLMResponse(
                text=data.get("response", ""),
                model_name=model,
                raw_usage={
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0)
                }
            )