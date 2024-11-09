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
from utils.convert_wav import convert_wav

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

    def create_prompt_book_title(self):
        prompt_book_title = f"""
        task: 本の構造化
        input_required:
            - book_content: {self.book_content}
            - total_pages: {self.n_pages}
            - target_readers: {self.target_readers}
            - additional_requirements: {self.additional_requirements}
        formatting_rules:
            writing_style: ですます調
        page_format:
            lines_per_page: 40
        title_format: 
            chapter_number: false  # 章番号を含めない
        content_requirements:
            book_level:
                title: required
                summary:
                min_sentences: 5
                max_sentences: 10
                must_include:
                    - 内容の要約
                    - 本の主な目的
                    - カバー範囲と深さ
            chapter_level:
                for_each_chapter:
                - title: required
                - summary: required
                - pages:
                    precision: 0.1
                    format: "0.0"
                - needsSubdivision:
                    type: boolean
                    purpose: 意味的凝集性の評価
        restrictions:
            - 推測情報を含めない
            - 未確認情報を含めない
        """
        return prompt_book_title

    def create_prompt_section_list_creation(self,book_title:str,book_summary:str,
                                            target:str,n_pages:str,section_summary:str):
        prompt_section_list_creation = f"""
        task: 本の特定部分の構造化
        input_required:
            - book_content: {self.book_content}
            - book_title: {book_title}
            - target_readers: {self.target_readers}
            - additional_requirements: {self.additional_requirements}
            - book_summary: {book_summary}
            - target: {target}
            - section_summary: {section_summary}
            - n_pages: {n_pages}
        formatting_rules:
            writing_style: ですます調
        page_format:
            lines_per_page: 40
        title_format:
            chapter_number: false    # 章番号を含めない
            section_number: false    # 節番号を含めない
        content_requirements:
            target_section:
            subdivide: true         # 複数パートへの分割を要求
            for_each_part:
                - title: required
                - summary: required
                - pages:
                    precision: 0.1
                    format: "0.0"
                - needsSubdivision:
                    type: boolean
                    purpose: 意味的凝集性の評価
        restrictions:
            - 推測情報を含めない
            - 未確認情報を含めない
        """
        return prompt_section_list_creation

    def create_prompt_content_creation(self,book_title:str,book_summary:str,target:str,n_pages:str,section_summary:str,equation_frequency:str):
        prompt_content_creation = f"""
        task: LaTex形式での本文生成
        input_required:
            - book_content: {self.book_content}
            - book_title: {book_title}
            - book_summary: {book_summary}
            - target: {target}
            - section_summary: {section_summary}
            - n_pages: {n_pages}
            - equation_frequency: {equation_frequency}
            - target_readers: {self.target_readers}
            - additional_requirements: {self.additional_requirements}
        formatting_rules:
            writing_style: ですます調
        page_format:
            lines_per_page: 40
        latex_format:
            document_class: false  # \\documentclass{{book}}を含めない
            preamble: false      # プリアンブルを含めない
            begin_document: false # \\begin{{document}}を含めない
            end_document: false   # \\end{{document}}を含めない
            equations:
                nesting: false    # 数式のネストを禁止
                format: "\\begin{{align*}} \\end{{align*}}"  # ネストしない形式を使用
            code_blocks:
                wrapper: "\\begin{{verbatim}} \\end{{verbatim}}"
            special_characters:
                escape_required:
                    "#": "\\#"    # #は\\#にエスケープ
                    "$": "\\$"    # $は\\$にエスケープ
                    "%": "\\%"    # %は\\%にエスケープ
                    "&": "\\&"    # &は\\&にエスケープ
                    "_": "\\_"    # _は\\_にエスケープ
                    "{{": "\\{{"  # {{は\\{{にエスケープ
                    "}}": "\\}}"  # }}は\\}}にエスケープ
                    "~": "\\~"    # ~は\\~にエスケープ
                    "^": "\\^"    # ^は\\^にエスケープ
                escape_method: "各特殊文字の前にバックスラッシュ（\\）を付けてエスケープする"
                example: |
                    入力例:
                        "Cost: $100 & discount: 25%"
                        "Section #2.1 {{main}} with footnote_1"
                        "Temperature: 20°C ~ 25°C ^ 2"
                    出力例:
                        "Cost: \\$100 \\& discount: 25\\%"
                        "Section \\#2.1 \\{{main\\}} with footnote\\_1"
                        "Temperature: 20°C \\~ 25°C \\^ 2"
        content_requirements:
            structure:
                header: false  # 見出しなし
                body: required # 本文のみ
            programming_content:
                sample_code: required_if_applicable # プログラミング関連の場合
        restrictions:
            - 推測情報を含めない
            - 未確認情報を含めない
            - 外部画像参照を含めない
            - 図解を含めない
            - LaTeXドキュメント構造を含めない
            - プリアンブルを含めない
        compilation:
            target: PDF
            compiler: latexmk
            requirements:
                - 全ての特殊文字をエスケープ
                - コンパイルエラーを防ぐ形式
                - 本文のみの出力（ドキュメント構造なし）
        output_format: Latex
        response_structure:
            format: |
            ```tex
            本文の内容
            ```
        """

        return prompt_content_creation

    def create_prompts(self):
        #1. 共通的なプロンプトを生成
        #self.common_prompt = self.create_common_prompt()
        #2. 本・章のタイトル，本・章の概要を記述したjsonを生成
        self.prompt_book_title = self.create_prompt_book_title()

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

    def async_gpt_responses(self, prompts, response_formats):                       
        try:
            responses = []
            # ThreadPoolExecutorで非同期にAPI呼び出し
            with ThreadPoolExecutor() as executor:
                # 各プロンプトに対して同期的にAPIを呼び出す
                futures = [
                    executor.submit(self.get_llm_response, prompt, response_formats[index])
                    for index, prompt in enumerate(prompts)
                ]
                # 結果を収集
                responses = [future.result() for future in futures]
            
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
            full_path = os.path.abspath(rename_path + ".pdf")

        except Exception as e:
            logging.error(f"Can't Create PDF File :  {e}")
            return False

        logging.info(f"{rename_path}.pdfの出力が完了しました")      
        return full_path

    def create_wav(self,filename:str,speaker:int):
        logging.info("5. wavファイルの生成を開始します")
        cw = convert_wav()
        cw.set_voicevox_speaker_id(speaker)
        wav_filename=cw.generate_wav(filename)
        logging.info(f" {wav_filename}の出力が完了しました")
        return wav_filename

# Define other functionalities as functions (skipped for brevity)

def main(book_content, target_readers, n_pages,level,wav):
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
    result = bookgenerator.create_pdf()
    
    if wav:
        bookgenerator.create_wav(result,wav)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a book using provided details.")
    parser.add_argument('book_content', type=str, help='内容')
    parser.add_argument('target_readers', type=str, help='対象読者')
    parser.add_argument('n_pages', type=int, help='ページ数')
    parser.add_argument('--level', type=str, help='数式の利用頻度', default=None)
    parser.add_argument('--wav', type=str, help='wavファイルの出力', default=None)

    args = parser.parse_args()

    main(args.book_content, args.target_readers, args.n_pages,args.level,args.wav)

