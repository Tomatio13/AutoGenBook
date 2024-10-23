import os
import re
import json
import openai
import anthropic
from pydantic import BaseModel
import logging
from dotenv import load_dotenv
from os.path import join, dirname

logger = logging.getLogger(__name__)
load_dotenv(verbose=True)
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

class llms:
    def __init__(self):
        # Determine which provider to use based on environment variables
        self.provider = os.environ.get("PROVIDER")
        self.model = os.environ.get("MODEL")
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.ollama_base_url=os.environ.get("OLLAMA_BASE_URL")
        self.ollama_max_tokens=os.environ.get("OLLAMA_MAX_TOKNES")

        if self.provider == "OPENAI":
            openai.api_key = self.openai_api_key
        elif self.provider == "ANTHROPIC":
            self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        elif self.provider =="OLLAMA":
            openai.base_url=self.ollama_base_url
            openai.api_key = "EMPTY"
        else:
            logger.error("Unknown PROVIDER specified in the environment variables.")

    def _call_openai_api(self, model: str, messages: list, response_format: BaseModel = None, temperature: float = 0.3,max_tokens: int = 1000):
        """
        Helper method to call the OpenAI API.
        """
        try:
            if response_format:
                return openai.beta.chat.completions.parse(
                    model=model,
                    messages=messages,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            return openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature
            )
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None

    def _call_claude_api(self, model: str, messages: list, response_format: BaseModel = None, temperature: float = 0.3,max_tokens: int = 1000 ) -> dict:
        """
        ClaudeのAPIを呼び出すヘルパーメソッド。指定されたPydanticモデルでのレスポンス形式をsystemメッセージに組み込みます。
        """
        try:
            # response_modelを用いたsystemメッセージの置換
            if response_format:
                model_example = response_format.schema_json(indent=2)
                existing_content = messages[0].get("content", "")
                systems= f"{existing_content}\nレスポンスは以下の形式に従ってください:\n{model_example}"
            else:
                systems = messages[0].get("content", "")
            if messages:
                del messages[0]

            response = self.client.messages.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=systems
            )

            return response
        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            return None

    def _call_ollama_api(self, model: str, messages: list, response_format: BaseModel = None, temperature: float = 0.3,max_tokens=256):
        """
        Helper method to call the OpenAI API.
        """
        try:
            if response_format:
                model_example = response_format.schema_json(indent=2)
                existing_content = messages[0].get("content", "")
                messages[0]["content"] = f"{existing_content}\nレスポンスは以下の形式に従ってください:\n{model_example}"

            return openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            return None
        
    def _call_api(self, messages: list, response_format: type = None, max_tokens: int = 8192, temperature: float = 0.3):
        """
        Call the appropriate API based on the provider.
        """
        if self.provider == "OPENAI":
            return self._call_openai_api(self.model, messages, response_format, temperature,max_tokens)
        elif self.provider == "ANTHROPIC":
            return self._call_claude_api(self.model, messages, response_format,temperature,max_tokens )
        elif self.provider == "OLLAMA":
            return self._call_ollama_api(self.model, messages, response_format,temperature,max_tokens=self.ollama_max_tokens )
        
    def _reponse_api(self,completion: dict,response_format: str):
        result=""
        if self.provider == "OPENAI":
            if response_format=="json":
                result = completion.choices[0].message.parsed.json()
            elif response_format=="parsed":
                result = completion.choices[0].message.parsed
            else:
                result = completion.choices[0].message.content
        elif self.provider=="ANTHROPIC":
            result = completion.content[0].text
            if response_format=="parsed":
                result = json.loads(result)
        elif self.provider=="OLLAMA":
            result = completion.choices[0].message.content
            if response_format=="parsed":
                result = json.loads(result)
            elif response_format=="json":
                result=self.get_json_string(result)

        return result
    
    def get_json_string(self,context:str):

        pattern = r'```json\s*(.*?)\s*```'
        match = re.search(pattern, context, re.DOTALL)

        if match:
            json_string = match.group(1)
            return json_string
        else:
            logging.info("JSONデータが見つかりませんでした。")
            return context
    
    def get_provider_name(self):
        return self.provider
    
    def get_model_name(self):
        return self.model
    
