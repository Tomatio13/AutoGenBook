import os
import re
import json
import logging
import random
import string
import networkx as nx
from dotenv import load_dotenv
from pylatex import Command, Document, Section, Subsection, Package,Figure
from pylatex.section import Chapter
from pylatex.utils import NoEscape
from typing import List
from pydantic import BaseModel
import argparse
from utils.models import llms
from utils.cover_image import cover_image
import asyncio
from concurrent.futures import ThreadPoolExecutor


class DirName(BaseModel):
    dirname: str

class SectionSummary(BaseModel):
    title: str
    summary: str
    n_pages: float
    needsSubdivision: bool

class SectionList(BaseModel):
    sectionlist: list[SectionSummary]

class BookSummary(BaseModel):
    title: str
    summary: str
    childs: list[SectionSummary]

class BookCover(BaseModel):
    title: str
    subtitle: str

# LLM
llms=llms()

class BookGenerator:
    def __init__(self):
        self._initialize_constants()
        self._create_output_directory()
        self._setup_logging()

    def _initialize_constants(self):
        """クラス内で使用する定数を初期化します。"""
        self.book_node_name = "book"
        self.max_depth = 5
        self.max_output_pages = 1.5
        self.base_dir = os.path.expanduser("output")
        self.equation_frequency_level = 1
        self.additional_requirements = ""

    def _create_output_directory(self):
        """出力ディレクトリが存在しない場合は作成します。"""
        os.makedirs(self.base_dir, mode=0o777, exist_ok=True)

    def _setup_logging(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def list_directories(self,base_directory: str) -> str:
        try:
            directories = [name for name in os.listdir(base_directory) if os.path.isdir(os.path.join(base_directory, name))]
            return ",".join(directories)
        except Exception as e:
            logging.error(f"Error listing directories: {e}")
            return ""

    def generate_random_folder_name(self,length=20):
        # 使用する文字を定義（小文字と数字）
        characters = string.ascii_lowercase + string.digits
        # ランダムに文字列を生成
        random_string = ''.join(random.choice(characters) for _ in range(length))
        return random_string

    def generate_dirname(self, title: str) -> str:
        """Generate a non-conflicting filename based on requirements."""
        try:
            existing_directories = self.list_directories(self.base_dir)
            user_input = (
                f"目的：下記のタイトルをベースとしての中身を要約したフォルダ名を生成してください。\n"
                f"条件：- ファイル名は、英数字・半角記号・小文字であること。\n"
                f"      - 文字列長さは20文字以内であること\n"
                f"      - 出力時にはファイル名のみを出力すること。\n"
                f"      - {existing_directories}は、カンマ区切りで既に存在するフォルダ名が記載されている。\n"
                f"        被らないように生成すること。\n"
                f"タイトル：\n{title}\n"
            )
            completion = llms._call_api(
                messages=[
                    {"role": "system", "content": "あなたは誠実で優秀なPythonプログラマです"},
                    {"role": "user", "content": user_input}
                ],
                response_format=DirName
            )
            if completion:
                json_data=llms._reponse_api(completion,"json")
                data = json.loads(json_data)
                if not data:
                    dirname_buff = self.generate_random_folder_name(20)
                    dirname = os.path.join(self.base_dir, dirname_buff, "")
                else:
                    dirname = os.path.join(self.base_dir, data.get("dirname", ""))
                return dirname
            return ""
        except Exception as e:
            logging.error(f"Error generating filename: {e}")
            return ""
    
    def create_homedir(self,title:str):
        try:
            self.home_dir = self.generate_dirname(title)
            os.makedirs(self.home_dir, exist_ok=True)
            self.latexmkrc_path = os.path.join(self.home_dir, ".latexmkrc")
        except Exception as e:
            logging.error(f"Error create directory at {self.home_dir}: {e}")
        return True
    
    def validate_inputs(self,book_content:str,target_readers: str,n_pages:int):
        is_valid = True

        if not book_content:
            logging.error("コンテンツを指定して下さい。")
            is_valid = False
        else:
            self.book_content = book_content

        if not target_readers:
            logging.error("ターゲットとなる読者を指定して下さい。")
            is_valid = False
        else:
            self.target_readers = target_readers

        if n_pages <= 0:
            logging.error("ページ数を指定してください。")
            is_valid = False
        else:
            self.n_pages = n_pages

        return is_valid

    def create_common_prompt(self):
        prompt_common = (
            f"以下の内容で本を執筆します．{self.book_content}"
            f"本全体のページ数は{self.n_pages}ページ，1ページあたり40行を想定しています．ですます調で記述してください．"
        )
        if self.target_readers:
            prompt_common += f"想定読者としては以下を考えています．\n {self.target_readers}"
        if self.additional_requirements:
            prompt_common += f"また，以下を考慮に入れてください．\n {self.additional_requirements}"
        return prompt_common

    def create_prompt_book_title(self,prompt_common:str):
        prompt_book_title = prompt_common + """
            以上をもとに，以下のようなjson形式で，本・章のタイトル，本・章の概要を示してください．
            本の概要には，内容の要約だけではなく，本の主な目的やカバーする内容の範囲と深さなどについても触れてください．5から10文ほどで，詳細にお願いします．
            また，各章に割くべきページ数を考えてください．ページ数は0.1単位で，0.8ページのように書いてください．
            それに加え，内容の意味的凝集性から考えて，各章を分節化する必要がありますかどうか（needsSubdivision）を考えてください．trueかfalseで答えてください．
            推測や未確認の情報は含めないでください．また，タイトルに第何章であるかは書かないでください．
            節の数は必要に応じて変えてください．
            """.strip()
        return prompt_book_title

    def create_prompt_section_list_creation(self,prompt_common:str,book_title:str,book_summary:str,
                                            target:str,n_pages:str,section_summary:str):

        prompt_section_list_creation = prompt_common + f"""
        以上の情報から，{book_title}というタイトルで本を作成しようと思います．本の概要を以下に示します．
        {book_summary}
        その中の{target}についての部分を{n_pages}ページで作成したいです．1ページあたり40行を想定しています．
        この部分の概要は，以下です．
        {section_summary}
        この部分を分節化して，複数のパートに分けて欲しいです．
        各パートのタイトルと概要を以下のようなjson形式にて出力してください．また，各パートに割くべきページ数を考えてください．ページ数は0.1単位で，0.8ページのように書いてください．
        それに加え，内容の意味的凝集性から考えて，各章を分節化する必要がありますかどうか（needsSubdivision）を考えてください．trueかfalseで答えてください．
        タイトルに第何章・節であるかは書かないでください．
        """
        return prompt_section_list_creation

    def create_prompt_content_creation(self,prompt_common:str,
                                       book_title:str,book_summary:str,target:str,n_pages:str,section_summary:str,equation_frequency:str):
        # 本文の内容の生成用プロンプト
        prompt_content_creation = prompt_common + f"""
        目的：以上の情報から，{book_title}というタイトルで本を作成しようと思います．本の概要を以下に示します．
        {book_summary}
        その中の{target}についての部分を{n_pages}ページで作成したいです．1ページあたり40行を想定しています．
        この部分の概要は，以下です．
        {section_summary}
        その部分の内容を{n_pages}分，つまり{n_pages} × 40行分をLaTeXで出力してください．プリアンブルで必要なライブラリはすべてインポートされています．
        推測や未確認の情報は含めないでください．見出しは必要なく，本文のみを出力してください．
        {equation_frequency}
        式をネストしないように，すなわち\\[ \\begin{{align*}} \\end{{align*}} \\]ではなく，\\begin{{align*}} \\end{{align*}}とするよう気をつけてください．
        本の内容がプログラミング言語の場合は、なるべく多くのサンプルコードも作成して下さい。
        コードを記述する際には、\\begin{{verbatim}} \\end{{verbatim}}で括るのを忘れないように気をつけください。
        条件：
        出力は、Latexを想定しており、Latexが持つ特殊記号・特殊文字の出力方法を考慮して下さい。
        - 説明文中にファイル名やメソッド名などを記述する際には、バッククォート（`）ではなく、\texttt{{}}で囲んで下さい。
        - 中括弧（{{ や }}）はバックスラッシュでエスケープする必要があります。具体的には、\\{{ と \\}} と書きます。
        - 説明文中にインライン数式を記述する場合、数式の前後を $と$で囲んで書いて下さい。具体的には、3 \times 2は$3 \times 2$と書きます。
        - ハッシュ(#)は、\\#と書いて下さい。
        - ドル($)は、\\$と書いて下さい。
        - percent(%)は、\\%と書いて下さい。
        - tilde(~)は\\textasciitildeと書いて下さい。
        - アンダースコア(_)は、\\_と書いて下さい。具体的には、説明分で変数名 my_networkを記述する場合は、my\\_networkと書きます。
        - caret(^)は\\textasciicircumと書いて下さい。backslash(\\)は\\textbackslashか、数式内の場合は\\backslashと書いて下さい。
        - 図解は不要です。外部のpngを参照するような記述はしないで下さい。
        上記の注意事項をよく読み、絶対に間違わないようにして下さい。
        出力形式：
        出力形式は以下のようにお願いします．
        ```tex
        本文の内容
        ```
        """
        return prompt_content_creation

    def create_prompts(self):
        #1. 共通的なプロンプトを生成
        self.common_prompt = self.create_common_prompt()
        #2. 本・章のタイトル，本・章の概要を記述したjsonを生成
        self.prompt_book_title = self.create_prompt_book_title(self.common_prompt)

        return True

    def create_book_graph(self):
        return nx.DiGraph(
            book_content=self.book_content,
            target_readers=self.target_readers,
            equation_frequency_level=self.equation_frequency_level,
            additional_requirements=self.additional_requirements
        )


    def initialize(self,book_content:str,target_readers:str,n_pages:int):
        logging.info("1. 初期化しています")
        self.validate_inputs(book_content,target_readers,n_pages)
        self.create_prompts()
        self.book_graph = self.create_book_graph()
        return True
    
    def set_equation_frequency_level(self,equation_frequency_level:int):
        self.equation_frequency_level=equation_frequency_level
        return True
    
    def generate_book_title_and_summary(self):
        logging.info("2. 本のタイトルと概要を生成を開始します")
        messages=[
            {"role": "system", "content": "あなたは誠実で優秀な日本人の作家です"},
            {"role": "user", "content": self.prompt_book_title}
        ]

        completion = llms._call_api(
             messages=messages,
            response_format=BookSummary
        )
        
        result=llms._reponse_api(completion,"json")
        book_json=json.loads(result)
        
        logging.info("本のタイトル：" + book_json["title"])
        logging.info("本の概要    ：" + book_json["summary"])

        # ディレクトリの作成
        self.create_homedir(book_json["title"])
        logging.info("ディレクトリ名:" + self.home_dir)

        # 本をグラフに追加
        self.book_graph.add_node(
            self.book_node_name,
            title=book_json["title"],
            summary=book_json["summary"],
            n_pages=self.n_pages,
            needsSubdivision=True
        )

        self.book_graph.add_nodes_from([(str(idx+1), child) for idx, child in enumerate(book_json["childs"])])
        self.book_graph.add_edges_from([(self.book_node_name, str(idx+1)) for idx in range(len(book_json["childs"]))])

        return True

    def extract_section_content(self,markdown_text):

        pattern = r'```tex\s*(.*?)\s*```'
        match = re.search(pattern, markdown_text, re.DOTALL)

        if match:
            tex_string = match.group(1)
            return tex_string
        else:
            logging.error("TeXデータが見つかりませんでした。")
            return None

    def get_equation_frequency(self,equation_frequency_level):
        if equation_frequency_level == 1:
            return "数式はほぼ使用せず、すべての概念を平易な言葉で説明してください。数式が絶対に必要な場合のみ、最小限の使用に留めてください。"
        elif equation_frequency_level == 2:
            return "数式は控えめに使用し、主に文章で説明を行ってください。必要な場合のみ簡単な数式を用いてください。"
        elif equation_frequency_level == 3:
            return "数式と文章による説明をバランス良く組み合わせてください。重要な概念は数式で表現し、それ以外は文章で補足してください。"
        elif equation_frequency_level == 4:
            return "数式を積極的に活用し、概念や関係性を正確に表現してください。ただし、重要な説明は文章でも補足してください。"
        elif equation_frequency_level == 5:
            return "数式を最大限に活用してください。可能な限り多くの概念や関係性を数式で表現してください．"


    def get_llm_response(self,prompt:str,response_format:type):
        messages=[
            {"role": "system", "content": "あなたは誠実で優秀な日本人の作家です"},
            {"role": "user", "content": prompt}
        ]

        completion = llms._call_api(
            messages=messages,
            response_format=response_format
        )

        return completion

    def async_gpt_responses(self,prompts,response_formats):                       
        try:
            # 新しいイベントループを作成して実行する
            responses = []
            
            # ThreadPoolExecutorで非同期にAPI呼び出し
            with ThreadPoolExecutor() as executor:
                loop = asyncio.new_event_loop()  # 新しいイベントループを作成
                asyncio.set_event_loop(loop)    # それを現在のループとして設定

                tasks = [
                    loop.run_in_executor(executor, self.get_llm_response, prompt, response_formats[index])
                    for index, prompt in enumerate(prompts)
                ]
                responses = loop.run_until_complete(asyncio.gather(*tasks))
                loop.close()  # イベントループを閉じる
            
            return responses
        except Exception as e:
            # エラーロギング
            logging.error(f"エラー: {str(e)}")
            raise ValueError(f"エラーが発生しました。{str(e)}")

    def generate_book_detail(self):
        logging.info("3. 章・節の内容を生成しています")
        self.book_node = self.book_graph.nodes[self.book_node_name]
        next_parent_list = [self.book_node_name]

        prompts_list=[]
        response_format_list=[]
        index_list=[]

        for depth in range(self.max_depth):
            parent_list = next_parent_list
            next_parent_list = []
            for parent_node_name in parent_list:
                prompts_list = []
                response_format_list=[]
                index_list=[]
                            
                for _, child_node_name in enumerate(self.book_graph.successors(parent_node_name)):
                    child_node = self.book_graph.nodes[child_node_name]
                    if (child_node["needsSubdivision"] or child_node["n_pages"] >= self.max_output_pages) and depth < self.max_depth-1:
                        
                        # LLMによる出力
                        prompt = self.create_prompt_section_list_creation(
                            self.common_prompt,
                            str(self.book_node["title"]),
                            str(self.book_node["summary"]),
                            str(child_node["title"]),
                            str(child_node["n_pages"]),
                            str(child_node["summary"])
                        )

                        prompts_list.append(prompt)
                        response_format_list.append(SectionList)
                        index_list.append("json")

                    elif not child_node["needsSubdivision"] or depth == self.max_depth-1:
                        prompt=self.create_prompt_content_creation(
                            self.common_prompt,
                            str(self.book_node["title"]),
                            str(self.book_node["summary"]),
                            str(child_node["title"]),
                            str(child_node["n_pages"]),
                            str(child_node["summary"]),
                            str(self.get_equation_frequency(self.book_graph.graph["equation_frequency_level"]))
                        )
                        prompts_list.append(prompt)
                        response_format_list.append("")
                        index_list.append("plain")
                    else:
                        logging.error("Error: needsSubdivision attribute is not set")
            
                # 並列でAPIを呼び出すぞ
                completions=self.async_gpt_responses(prompts_list,response_format_list)

                for index, child_node_name in enumerate(self.book_graph.successors(parent_node_name)):
                    index_str=index_list[index]
                    completion=completions[index]

                    if index_str=="json":
                        result=llms._reponse_api(completion,"json") 
                        data=json.loads(result)
                        section_json = data.get("sectionlist", [])
                        
                        # グラフノードの作成・結果の格納
                        self.book_graph.add_nodes_from([(child_node_name + "-" + str(idx+1), grandchild) for idx, grandchild in enumerate(section_json)])
                        self.book_graph.add_edges_from([(child_node_name, child_node_name + "-" + str(idx+1)) for idx in range(len(section_json))])

                        # 分節化した場合のみ次の親になる
                        next_parent_list.append(child_node_name)
                    else:
                        result=llms._reponse_api(completion,"")
                        # 出力をファイルに保存
                        contents_tex = self.extract_section_content(result)
                        contents_filename=os.path.join(self.home_dir,str(child_node_name)+"-p.tex")
                        with open(contents_filename, mode='w', encoding='UTF-8') as f:
                            f.write(contents_tex)

                        # グラフノードの作成・結果の格納
                        self.book_graph.add_nodes_from([(child_node_name + "-p", {"content_file_path": contents_filename})])
                        self.book_graph.add_edges_from([(child_node_name, child_node_name + "-p")])


    # ここからPDFの整形に関わる処理

    def create_latexmkrc(self):
        content = """$latex = 'platex -synctex=1 -halt-on-error -interaction=nonstopmode -file-line-error %O %S';
                    $bibtex = 'pbibtex %O %S';
                    $biber = 'biber --bblencoding=utf8 -u -U --output_safechars %O %S';
                    $makeindex = 'mendex %O -o %D %S';
                    $dvipdf = 'dvipdfmx %O -o %D %S';
                    $max_repeat = 5;
                    $pdf_mode = 3;"""
        
        # .latexmkrcを出力
        with open(self.latexmkrc_path, "w") as file:
            file.write(content)

    def extract_content_list(self,string_list):
        # この関数は、入力されたstring_listから特定のパターン（数字とハイフンの組み合わせで'-p'で終わる）
        # にマッチする文字列のみを抽出し、新しいリストとして返す
        pattern = r'(?:\d+-)*\d+-p'
        return [s for s in string_list if re.match(pattern, s)]

    def custom_sort_key(self,s):
        # この関数は、文字列sを数字の部分で分割し、それらを整数のリストに変換する
        # これにより、数値的な順序でソートするためのカスタムキーを生成する
        parts = re.split(r'[-p]', s)
        return [int(part) for part in parts if part != '']

    def sort_strings(self,string_list):
        # この関数は、入力されたstring_listを、custom_sort_key関数で定義された
        # カスタムキーを使用してソートし、ソートされた新しいリストを返す
        sorted_strings = sorted(string_list, key=self.custom_sort_key)
        return sorted_strings

    def create_cover_iamge(self,title:str,summary:str):
        # LLMによる出力
        prompt = (
            f"目的：下記のタイトルと概要をベースとして英名のタイトルと、サブタイトルを生成して下さい。\n"
            f"条件：英名は20文字以内にして下さい"
            f"タイトル：\n{title}\n"
            f"概要：\n{summary}\n"
            )
        
        completion=self.get_llm_response(prompt,BookCover)
        result=llms._reponse_api(completion,"json") 

        data=json.loads(result)
        en_title = data.get("title")
        en_subtitle=""
        author=llms.get_provider_name()+":"+llms.get_model_name()
        image_Number=str(random.randint(1,40))
        theme = str(random.randint(0, 16))

        ci = cover_image()
        image_path=ci.generate_image(
            self.home_dir,
            en_title,
            en_subtitle, 
            author,  
            image_Number, 
            theme, 
            'bottom_right', 
            'The Definitive Guide'
        )
        return image_path

    def create_pdf(self):
        logging.info("4. PDFの生成を開始します")
        self.create_latexmkrc()

        cover_image_path=self.create_cover_iamge(
            self.book_node["title"],
            self.book_node["summary"]
        )

        logging.info("カバー画像:" + cover_image_path)
        try:
            # pylatexにより、PDFを作成

            # プリアンブル・タイトルの追加
            geometry_options = {"tmargin": "3cm", "lmargin": "3cm"}
            doc = Document(documentclass="jsreport", geometry_options=geometry_options)
            # 表紙画像の挿入
            with doc.create(Figure(position='h!')) as cover:
                cover.add_image(cover_image_path, width=NoEscape(r'1\textwidth'))
     
            # プリアンブル・タイトルの追加
            doc.packages.append(Package('amsmath'))
            doc.packages.append(Package('amssymb'))
            doc.packages.append(Package('amsfonts'))
            doc.packages.append(Package('mathtools'))
            doc.packages.append(Package('bm'))
            doc.packages.append(Package('physics'))
            doc.packages.append(Package('inputenc', options="utf8"))
            doc.preamble.append(Command("title", self.book_graph.nodes[self.book_node_name]["title"]))
            doc.preamble.append(Command("date", NoEscape(r"\today")))
            doc.append(NoEscape(r"\maketitle"))
            doc.append(NoEscape(r"\tableofcontents"))

            # 本文の内容を持つノードを順番に並び替え
            content_str_list = self.extract_content_list(list(self.book_graph.nodes))
            sorted_content_str_list = self.sort_strings(content_str_list)

            # 本文の追加
            for heading_number_str in sorted_content_str_list:
                heading_number = self.custom_sort_key(heading_number_str)

                # 章の見出しの追加
                if len(heading_number[1:]) == 0 or all(x == 1 for x in heading_number[1:]):
                    node_name = "-".join(map(str, heading_number[0:1]))
                    with doc.create(Chapter(self.book_graph.nodes[node_name]["title"], label=False)):
                        doc.append(NoEscape(self.book_graph.nodes[node_name]["summary"].replace("\\\\","\\")))

                # 節の見出しの追加
                if (len(heading_number[2:]) == 0 and len(heading_number[:2]) > 1) or (len(heading_number[2:]) > 0 and all(x == 1 for x in heading_number[2:])):
                    node_name = "-".join(map(str, heading_number[0:2]))
                    with doc.create(Section(self.book_graph.nodes[node_name]["title"], label=False)):
                        doc.append(NoEscape(self.book_graph.nodes[node_name]["summary"].replace("\\\\","\\")))

                # 小節の見出しの追加
                if (len(heading_number[3:]) == 0 and len(heading_number[:3]) > 2) or (len(heading_number[3:]) > 0 and all(x == 1 for x in heading_number[3:])):
                    node_name = "-".join(map(str, heading_number[0:3]))
                    with doc.create(Subsection(self.book_graph.nodes[node_name]["title"], label=False)):
                        doc.append(NoEscape(self.book_graph.nodes[node_name]["summary"].replace("\\\\","\\")))

                # 本文の追加
                tex_file_path = self.book_graph.nodes[heading_number_str]["content_file_path"]
                with open(tex_file_path, "r", encoding='UTF-8') as file:
                    tex_content = file.read()
                    doc.append(NoEscape(tex_content))

            # 日本語はエラーになる場合があるので英名で作成してからリネームする
            output_path= os.path.join(self.home_dir,os.path.basename(self.home_dir))
            # doc.generate_pdf(self.book_node["title"], compiler="latexmk", clean_tex=False) 
            doc.generate_pdf(output_path, compiler="latexmk", clean_tex=False) 

            rename_path=os.path.join(self.home_dir,self.book_node['title'])
            os.rename(output_path+".pdf",rename_path+".pdf")

        except Exception as e:
            logging.error(f"Can't Create PDF File :  {e}")

        logging.info(f"{rename_path}.pdfの出力が完了しました")      

# Define other functionalities as functions (skipped for brevity)

def main(book_content, target_readers, n_pages,level):
    bookgenerator = BookGenerator()
    # 初期化
    bookgenerator.initialize(book_content, target_readers, n_pages)

    if level:
        bookgenerator.set_equation_frequency_level(level)

    # 本の概要を生成
    bookgenerator.generate_book_title_and_summary()
    # 本の中身を生成
    bookgenerator.generate_book_detail()
    # PDFを生成
    bookgenerator.create_pdf()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a book using provided details.")
    parser.add_argument('book_content', type=str, help='内容')
    parser.add_argument('target_readers', type=str, help='対象読者')
    parser.add_argument('n_pages', type=int, help='ページ数')
    parser.add_argument('--level', type=str, help='数式の利用頻度', default=None)

    args = parser.parse_args()

    main(args.book_content, args.target_readers, args.n_pages,args.level)
