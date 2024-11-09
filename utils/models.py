import os
import re
import json
import openai
import anthropic
from pydantic import BaseModel
import logging
from dotenv import load_dotenv
from os.path import join, dirname
import time

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
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        self.gemini_base_url=os.environ.get("GEMINI_BASE_URL")

        if self.provider == "OPENAI":
            openai.api_key = self.openai_api_key
        elif self.provider == "ANTHROPIC":
            self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        elif self.provider =="OLLAMA":
            openai.base_url=self.ollama_base_url
            openai.api_key = "EMPTY"
        elif self.provider == "GEMINI":
            openai.api_key = self.gemini_api_key
            openai.base_url=self.gemini_base_url
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
                schema = response_format.model_json_schema()
                model_example = json.dumps(schema, indent=2)
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
        Helper method to call the Ollama API.
        """
        try:
            if response_format:
                schema = response_format.model_json_schema()
                model_example = json.dumps(schema, indent=2)
                existing_content = messages[0].get("content", "")                
                messages[0]["content"] = f"{existing_content}\nレスポンスは以下の形式に従ってください。:\n{model_example}"
            return openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            return None
        
    def _call_gemini_api(self, model: str, messages: list, response_format: BaseModel = None, temperature: float = 0.3):
        """
        Helper method to call the Gemini API.
        """

        time.sleep(0.5)

        try:
            if response_format:
                model_example = self.generate_json_example(response_format)
                existing_content = messages[0].get("content", "")
                messages[0]["content"] = f"{existing_content}\nレスポンスは以下の形式に従ってください。```jsonと```で括って下さい。:\n{model_example}。返信時にJSONフォーマット定義を先頭に入れる必要はありません。"
            return openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature
            )
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
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
        elif self.provider == "GEMINI":
            return self._call_gemini_api(self.model, messages, response_format,temperature)
        
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
        elif self.provider=="OLLAMA" or self.provider == "GEMINI":
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
    
    def generate_json_example(self,model: BaseModel) -> str:
        def create_example_data(field_type):
            # フィールドがBaseModelのサブクラスの場合、再帰的に例を生成
            if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                return {field: create_example_data(sub_field.annotation) for field, sub_field in field_type.__fields__.items()}
            # フィールドがリストの場合、リストの要素タイプに基づき例を生成
            elif hasattr(field_type, "__origin__") and field_type.__origin__ == list:
                element_type = field_type.__args__[0]
                return [create_example_data(element_type)]
            # それ以外のフィールドにはプレースホルダー値を設定
            else:
                return "ここに値" if field_type == str else 0 if field_type == int else 0.0 if field_type == float else False

        # モデル全体のJSON例を作成
        example_data = {field: create_example_data(field_info.annotation) for field, field_info in model.__fields__.items()}
        example_instance = model.parse_obj(example_data)
        return example_instance.json()


    def get_provider_name(self):
        return self.provider
    
    def get_model_name(self):
        return self.model
    
