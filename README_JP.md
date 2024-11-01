# AutoGenBook
AutoGenBookは、LLMを使用して自動的に本を生成するPythonベースのツールです。ユーザーが定義したコンテンツに基づいて、章、セクション、サブセクションを再帰的に作成し、最終的な本をLaTeXを使用してPDFとして出力します。

# 変更点
[hooked-on-mas](https://github.com/hooked-on-mas/AutoGenBook)によって作成されたAutoGenBookに対して、以下の修正が行われました：
- LLM:
  - OpenAIに加えてClaude/Ollamaから選択できるように変更
- 実行環境:
  - Google ColabからDockerコンテナとコマンドラインでの実行に変更
- コンテンツ:
  - O'REILLY風のカバーを追加
  - プログラミング言語のサンプルコードの掲載を増加

## 使用方法

1. リポジトリをクローンします：
   ```bash
   git clone https://github.com/Tomatio13/AutoGenBook.git
   cd AutoGenBook
   ```

2. .envファイルにAPI_KEYを指定します：1つのPROVIDERとMODELを必ず指定する必要があります。

   ```bash
   cp -p env.example .env
   ```
   
   ```bash
   PROVIDER=ANTHROPIC
   MODEL=claude-3-5-sonnet-20240620
   ANTHROPIC_API_KEY=<あなたのClaude APIキー>

   # PROVIDER=OPENAI
   # MODEL=gpt-4o
   # OPENAI_API_KEY=<あなたのOpenAI APIキー>

   #PROVIDER=OLLAMA
   #MODEL=qwen2.5-coder:latest
   #OLLAMA_BASE_URL=http://localhost:11434/v1/
   #OLLAMA_MAX_TOKENS=256
   ```
    *注意*
    Ollamaを指定することもできますが、MODELのmax_tokensとnum_ctxが小さいため、生成に失敗することが多く、推奨されません。

3. コンテナをビルドします。
   ```bash
   docker compose build  
   ```

4. コンテナを起動します。
   ```bash
   docker compose up -d 
   ```

5. ターミナルで以下のコマンドを実行します：
   ```bash
    docker exec autogenbook-autogenbook-1 python AutoGenBook.py "Next.jsに関する教科書" "Next.js初学者" 5

    [実行ログは同じなので省略...]
   ```

6. PDFファイルがoutputフォルダの下に出力されます。
   ステップ5の例では、"output/py_prog_getting_st"フォルダに"Pythonプログラミング入門.pdf"というファイル名で出力されます。

## AutoGenBook.pyの使用方法

`AutoGenBook.py`は本を生成するためのスクリプトです。指定されたコンテンツ、対象読者、ページ数に基づいて本を作成します。

### コマンドライン引数

- `book_content`（必須）：本の内容に関する情報を指定します。
- `target_readers`（必須）：本の対象読者を定義します。
- `n_pages`（必須）：本のページ数を指定します。
- `--level LEVEL`（オプション）：数式の使用レベルを指定します。

### 使用例

以下は`AutoGenBook.py`の基本的な使用例です：

```bash
docker exec autogenbook-autogenbook-1 python AutoGenBook.py "本の内容" "若い成人" 150 --level intermediate
```

### PDF変換時の対処
texまでは作成されたが最後にPDFに変換できない場合は、以下のようにしてみてください。
```bash
docker exec -it autogenbook-autogenbook-1 /bin/bash
cd output/py_prog_getting_st
vi py_prog_getting_st.log
((変換が失敗している箇所が最後の方に記載されているので、失敗箇所を確認して下さい))
vi py_prog_getting_st.tex
((変換が失敗している箇所を確認して、修正して下さい))
latexmk -pdfdvi -pv  py_prog_getting_st.tex
```
latexmkを何回か実行-->ログの確認-->再度コンパイルを繰り返すとPDFに変換できる場合があります。

### 数式表現の使用レベル
1: ほとんど数式を使用せず、すべての概念を平易な言葉で説明します。数式は絶対に必要な場合のみ最小限使用します。

2: 数式の使用を控えめにし、主にテキストでの説明に重点を置きます。必要な場合のみ簡単な数式を使用します。

3: 数式とテキストによる説明をバランスよく組み合わせます。重要な概念は数式で表現し、それ以外はテキストで補足します。

4: 概念や関係を正確に表現するために数式を積極的に使用します。ただし、重要な説明はテキストでも提供します。

5: 数式を最大限活用します。できるだけ多くの概念や関係を数式で表現します。

## APIエンドポイント

サービスは`http://localhost:8100`で実行されます。

### 1. 本の生成開始

**エンドポイント**: `POST /generate-book`

**リクエストボディ**:
```json
{
    "book_content": "本の内容の説明",
    "target_readers": "対象読者の説明",
    "n_pages": 50,
    "level": 1  // オプション：数式の使用頻度（1-5）
}
```

**レスポンス**:
```json
{
    "status": "accepted",
    "message": "本の生成を開始しました",
    "task_id": "生成されたタスクID",
    "author": null
}
```

### 2. タスク状態の確認

**エンドポイント**: `GET /task/{task_id}`

**レスポンス**:
```json
{
    "status": "completed",  // "processing", "completed", "failed"
    "output_dir": "出力ディレクトリのパス",
    "title": "生成された本のタイトル",
    "author": "PROVIDER:MODEL_NAME"  // 例："OPENAI:gpt-4"または"ANTHROPIC:claude-3-sonnet"
}
```

### 3. PDFのダウンロード

**エンドポイント**: `GET /download/{task_id}`

生成されたPDF本をダウンロードします。タスクが完了している場合のみ利用可能です。

### 4. カバー画像のダウンロード

**エンドポイント**: `GET /download-cover/{task_id}`

生成されたカバー画像をPNG形式でダウンロードします。タスクが完了している場合のみ利用可能です。

### 5. ヘルスチェック

**エンドポイント**: `GET /health`

**レスポンス**:
```json
{
    "status": "healthy"
}
```

## 使用例

1. 本の生成をリクエスト：
```bash
curl -X POST "http://localhost:8100/generate-book" \
     -H "Content-Type: application/json" \
     -d '{
           "book_content": "Pythonプログラミング入門",
           "target_readers": "プログラミング初心者",
           "n_pages": 50,
           "level": 1
         }'
```

2. タスク状態の確認：
```bash
curl "http://localhost:8100/task/{task_id}"
```

3. PDFのダウンロード：
```bash
curl -O -J "http://localhost:8100/download/{task_id}"
```

4. カバー画像のダウンロード：
```bash
curl -O -J "http://localhost:8100/download-cover/{task_id}"
```

## APIドキュメント

Swagger UIを使用したAPIドキュメントは以下で利用可能です：
- http://localhost:8100/docs
- http://localhost:8100/redoc

# 謝辞
O'REILLY風のカバー画像は、[O-RLY-Book-GeneratorPublic](https://github.com/charleshberlin/O-RLY-Book-Generator.git)のソースコードを基に作成されました。