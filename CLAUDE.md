# CLAUDE.md — Email Agent (Python + Ollama)

## 🛠 Build & Development
- **Environment:** venv or conda
- **Install:** pip install -r requirements.txt
- **Run Agent:** python main.py
- **Lint:** flake8 . or black .

## 🧪 Testing Commands
- **All Tests:** pytest
- **Single Test:** pytest <file_path>
- **Watch:** pytest-watch

## 📐 Architecture & Standards
- **Tech Stack:** Python 3.12+, Ollama (Local LLM), [mention any libs like LangChain or FastAPI]
- **Style:** PEP 8 compliance, use type hints, prefer async/await for I/O tasks.
- **Logic:** Email processing flows through `processor.py`; Ollama integration lives in `llm_client.py`.

## 🤖 Agentic Rules (Strict)
- **Local Context:** You are running on a 16GB M1 via Ollama. Keep responses concise to save KV cache.
- **File Access:** Always check `downloads/` for new files before generating summaries.
- **Ollama:** Use the qwen-128k:latest model for all reasoning tasks.

## 📍 Key Directories
- `downloads/`: Raw files to be summarized.
- `output/`: Generated summaries and logs.
- `src/utils/`: Helper functions for email parsing.
