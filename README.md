# 📚 ScholarPath

> **AI-powered academic paper analyzer** that extracts claims from research PDFs, verifies them against real published papers, and auto-generates a personalized learning roadmap — deployed and live.

[![Live Demo](https://img.shields.io/badge/Live-Demo-brightgreen?style=for-the-badge)](https://scholar-path-tau.vercel.app)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react)](https://react.dev)
[![Supabase](https://img.shields.io/badge/Supabase-Auth-3ECF8E?style=for-the-badge&logo=supabase)](https://supabase.com)
[![CrewAI](https://img.shields.io/badge/CrewAI-Multi--Agent-orange?style=for-the-badge)](https://crewai.com)

---

## 🌐 Live Application

**Frontend:** [https://scholar-path-tau.vercel.app](https://scholar-path-tau.vercel.app)  
**Backend API:** Hosted on Render (FastAPI)

---

## 🧠 What It Does

ScholarPath is a full-stack AI research tool that helps students and researchers **understand academic papers faster**. Upload any research PDF and ScholarPath will:

1. **Parse the PDF** — extracts full text, reference lists, inline citations, and clickable hyperlinks
2. **Extract claims** — identifies every assertion in the paper that is backed by a citation
3. **Verify claims against real papers** — fetches matching paper metadata from the Semantic Scholar API and scores each claim (0–100) using a Groq-hosted LLaMA 3.1 model
4. **Generate a learning roadmap** — a CrewAI multi-agent pipeline synthesizes all verified topics into an ordered, visual, node-based study plan rendered with React Flow
5. **Persist history** — all analyses are saved per-user via Supabase so you can revisit past results

---

## ✨ Key Features

| Feature                    | Details                                                                                         |
| -------------------------- | ----------------------------------------------------------------------------------------------- |
| 📄 **PDF Intelligence**    | Full text extraction + regex citation parsing + spatial hyperlink extraction via PyMuPDF        |
| 🔍 **Claim Verification**  | Semantic Scholar API lookup → LLM similarity scoring (0–100) with colour-coded confidence       |
| 🤖 **Multi-Agent Roadmap** | CrewAI crew with dedicated `Academic Claim Verifier` and `Educational Roadmap Generator` agents |
| 🗺️ **Interactive Roadmap** | Directed node graph rendered with `@xyflow/react` (React Flow)                                  |
| 🔐 **Auth & History**      | Supabase authentication + persistent `uploads_history` table per user                           |
| ⚡ **Fast Inference**      | Groq `llama-3.1-8b-instant` for near-instant LLM responses                                      |

---

## 🏗️ Architecture

```
┌─────────────────────────────────┐      ┌──────────────────────────────────┐
│         React Frontend          │      │        FastAPI Backend            │
│  (Vite · React 19 · React Flow) │◄────►│  /upload endpoint                │
│  Supabase Auth · tsParticles    │      │  ├── pdf_parser.py (PyMuPDF)     │
└─────────────────────────────────┘      │  ├── paper_fetcher.py (Sem.Sch.) │
                                         │  ├── claim_verifier.py (Groq)    │
                                         │  └── crew/ (CrewAI agents)       │
                                         └────────────────┬─────────────────┘
                                                          │
                                            ┌─────────────▼──────────────┐
                                            │  External APIs              │
                                            │  · Semantic Scholar Graph   │
                                            │  · Groq (LLaMA 3.1 8B)     │
                                            │  · Supabase (Postgres DB)   │
                                            └────────────────────────────┘
```

---

## 🛠️ Tech Stack

### Backend

| Technology               | Role                                 |
| ------------------------ | ------------------------------------ |
| **FastAPI**              | REST API framework                   |
| **PyMuPDF (fitz)**       | PDF text & hyperlink extraction      |
| **CrewAI**               | Multi-agent orchestration            |
| **Groq API**             | LLM inference (LLaMA 3.1 8B Instant) |
| **Semantic Scholar API** | Academic paper metadata lookup       |
| **python-dotenv**        | Environment variable management      |
| **Uvicorn**              | ASGI server                          |

### Frontend

| Technology             | Role                           |
| ---------------------- | ------------------------------ |
| **React 19**           | UI framework                   |
| **Vite**               | Build tool & dev server        |
| **@xyflow/react**      | Interactive roadmap node graph |
| **@tsparticles/react** | Animated particle background   |
| **Supabase JS**        | Auth & database client         |

---

## 🚀 Local Setup

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** and **npm**
- A free **Groq API key** — [console.groq.com](https://console.groq.com)
- A free **Supabase project** — [supabase.com](https://supabase.com)

---

### 1. Clone the Repository

```bash
git clone https://github.com/K10rakesh/ScholarPath.git
cd ScholarPath
```

---

### 2. Backend Setup

```bash
# Install Python dependencies
pip install -r requirements.txt
```

Create a `.env` file in the **project root**:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Start the FastAPI server:

```bash
uvicorn backend.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

---

### 3. Frontend Setup

```bash
cd frontend
npm install
```

Create a `.env` file inside the `frontend/` directory:

```env
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

> **Supabase Setup:** In your Supabase project, create a table called `uploads_history` with columns: `id` (uuid, PK), `user_id` (uuid), `filename` (text), `analysis_data` (jsonb), `created_at` (timestamptz, default `now()`).

Start the frontend dev server:

```bash
npm run dev
```

The app will be available at `http://localhost:5173`.

---

### 4. Usage

1. Open `http://localhost:5173` and sign in / create an account
2. Upload any academic research PDF (`.pdf`)
3. Wait for the pipeline to process (typically 30–90 seconds depending on paper length)
4. Explore your **Verified Topics** (colour-coded by confidence score) and the **Interactive Roadmap**
5. Past analyses are saved in your sidebar history

---

## 📁 Project Structure

```
scholarpath/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── routes/
│   │   └── upload.py            # /upload endpoint
│   ├── services/
│   │   ├── pdf_parser.py        # PDF text + citation extraction
│   │   ├── paper_fetcher.py     # Semantic Scholar paper lookup
│   │   ├── claim_verifier.py    # Groq LLM claim scoring
│   │   └── roadmap.py           # Roadmap data assembly
│   └── crew/
│       ├── agents.py            # CrewAI agent definitions
│       ├── tasks.py             # CrewAI task definitions
│       └── crew.py              # Crew orchestration
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main app + upload logic
│   │   ├── components/
│   │   │   ├── Auth.jsx         # Supabase auth UI
│   │   │   ├── RoadmapFlow.jsx  # React Flow roadmap graph
│   │   │   └── ParticlesBackground.jsx
│   │   └── supabaseClient.js
│   ├── package.json
│   └── vite.config.js
├── requirements.txt
└── README.md
```

---

## 🤖 AI Pipeline

```
PDF Upload
    │
    ▼
pdf_parser.py  ──►  Extract text, references, and cited claims
    │
    ▼
paper_fetcher.py ──►  Query Semantic Scholar for each reference
    │
    ▼
claim_verifier.py ──►  Score each claim vs paper abstract (Groq LLaMA 3.1)
    │
    ▼
CrewAI Crew  ──►  Agent 1: Verify top topics
              ──►  Agent 2: Generate ordered learning roadmap
    │
    ▼
React Flow  ──►  Render interactive roadmap graph in the browser
```

---

## 🌍 Deployment

| Layer           | Platform                                            |
| --------------- | --------------------------------------------------- |
| Frontend        | **Vercel** (auto-deploy from `frontend/` directory) |
| Backend         | **Render** (FastAPI via `uvicorn backend.main:app`) |
| Database / Auth | **Supabase**                                        |

---
