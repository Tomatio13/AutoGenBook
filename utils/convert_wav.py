import requests
from pydub import AudioSegment
import pymupdf
import argparse
from dotenv import load_dotenv
from os.path import join, dirname
import os
import logging

from .models import llms

logger = logging.getLogger(__name__)
load_dotenv(verbose=True)
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

class convert_wav:

    def __init__(self):
        self.voice_kind=os.environ.get("VOICE_KIND")
        if self.voice_kind=="VOICEVOX":
            self.voice_api_url=os.environ.get("VOICEVOX_API_URL")
        elif self.voice_kind=="AIVIS":
            self.voice_api_url=os.environ.get("AIVSISPEECH_API_URL")
        else:
            logger.error("VOICE_KIND is not set")
            raise ValueError("VOICE_KIND is not set")
        logger.info(f"voice_kind: {self.voice_kind}")
        logger.info(f"voice_api_url: {self.voice_api_url}")

    def split_text(self,text, max_length=1000):
        return [text[i:i + max_length] for i in range(0, len(text), max_length)]
    
    def convert_to_japanese(self, text):
        """
        テキスト内の英数字や記号を日本語に変換する
        """
        try:
            llm = llms()
            prompt = (
                f"以下のテキストを全て日本語のひらがなに変換してください。\n"
                f"漢字、カタカナ、アルファベット、記号は全て変換してください。\n"
                f"文章の意味や文節を意識し、適切な日本語(ひらがな)に変換してください。\n"
                f"省略せずにすべて変換して下さい。ただし、目次ページは全体的に省略して下さい。\n"
                f"入力テキスト：\n{text}\n"
                f"出力テキスト：変換後のテキストのみを出力してください。\n"
            )
            messages=[
                {"role": "system", "content": "あなたは誠実で優秀な日本語変換家です"},
                {"role": "user", "content": prompt}
            ]
            completion = llm._call_api(
                messages=messages,
                temperature=0.3
            )
            
            if completion:
                result=llm._reponse_api(completion,"")
                return result
            else:
                logger.error("LLMからの応答の取得に失敗しました")
                return text
                
        except Exception as e:
            logger.error(f"日本語変換処理でエラーが発生しました: {e}")
            return text

    def generate_query(self,text, url=None, speaker=1):
        query_payload={'text': text,'speaker': speaker}
        url=url+"/audio_query"
        response= requests.post(url,params=query_payload)

        if response.status_code != 200:
            print(f"Eroor in audio_eury: {response.text}")
            return

        query=response.json()
        return query

    def generate_audio(self,query, index,pdf_dir,url=None,speaker=1):
        payload={"speaker": speaker}
        url=url+"/synthesis"
        response = requests.post(url, params=payload,json=query)
        
        if response.status_code == 200:
            with open(os.path.join(pdf_dir,f"output_{index}.wav"), "wb") as f:
                f.write(response.content)
        else:
            print(f"Error: {response.status_code}")

    def pdf2text(self,filename:str):
        try:
            if not os.path.exists(filename):
                logging.error(f"PDFファイルが見つかりません: {filename}")
                raise FileNotFoundError(f"PDFファイルが見つかりません: {filename}")
            
            doc = pymupdf.open(filename)
            if doc.page_count == 0:
                logging.error(f"PDFファイルにページが含まれていません: {filename}")
                raise ValueError("PDFファイルにページが含まれていません")
                
            text = ""
            for page in doc:
                text += page.get_text()
            
            if not text.strip():
                logging.error("PDFファイルからテキストを抽出できませんでした")
                raise ValueError("PDFファイルからテキストを抽出できませんでした")
                
            return text
            
        except pymupdf.fitz.FileDataError:
            logging.error(f"無効なPDFファイルです: {filename}")
            raise ValueError(f"無効なPDFファイルです: {filename}")
        except Exception as e:
            logging.error(f"PDFファイルの処理中にエラーが発生しました: {filename}")
            raise Exception(f"PDFファイルの処理中にエラーが発生しました: {str(e)}")
        finally:
            if 'doc' in locals():
                doc.close()

    def generate_wav(self,filename:str):
        logging.info(f"Converting {filename} to wav Started")
        pdf_path = os.path.abspath(os.path.join(os.path.dirname( __file__ ),  '..',filename))
        pdf_dir=os.path.dirname(pdf_path)
        text=self.pdf2text(pdf_path)

        split_texts = self.split_text(text)
        logging.info(f"Converting {filename} to wav text split into {len(split_texts)} parts")
        logging.info(f"speaker: {self.voice_speaker_id}")
        for i, part in enumerate(split_texts):
            part=self.convert_to_japanese(part)
            logging.info(f"Converting {filename} to wav text extracted")
            query=self.generate_query(part,self.voice_api_url,self.voice_speaker_id)
            self.generate_audio(query, i,pdf_dir,self.voice_api_url,self.voice_speaker_id)
            logging.info(f"Converting {filename} to wav audio file {i} generated")

        output_filename=self.set_output_filename(pdf_path)
        self.combine_audio_files_with_name(len(split_texts),pdf_dir,output_filename)
        logging.info(f"Converting {filename} to wav Finished")
        return output_filename

    def set_output_filename(self, filename: str):
        # PDFファイル名から拡張子を除去してwav拡張子を付与
        base_name = os.path.splitext(filename)[0]
        return f"{base_name}.wav"

    def combine_audio_files_with_name(self, num_files, pdf_dir, output_filename):
        combined = AudioSegment.empty()
        for i in range(num_files):
            audio = AudioSegment.from_wav(os.path.join(pdf_dir,f"output_{i}.wav"))
            combined += audio
            # 一時ファイルを削除
            os.remove(os.path.join(pdf_dir,f"output_{i}.wav"))
        combined.export(output_filename, format="wav")

    def set_voice_url(self,url):
        self.voice_api_url=url

    def set_voice_speaker_id(self,speaker_id):
        self.voice_speaker_id=speaker_id

def main(filename, url, speaker):
    cw = convert_wav()
    cw.set_voice_url(url)
    cw.set_voice_speaker_id(speaker) 
    filename=cw.generate_wav(filename)
    return filename

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a wav file from a pdf file.")
    parser.add_argument('filename', type=str, help='pdf file name')
    parser.add_argument('url', type=str, help='use voicevox url')
    parser.add_argument('speaker', type=int, help='speaker number')

    args = parser.parse_args()

    filename=main(args.filename, args.url, args.speaker)
    print(filename)
