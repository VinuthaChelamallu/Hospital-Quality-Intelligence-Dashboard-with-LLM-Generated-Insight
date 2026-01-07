# AI-Assisted Hospital Quality & Performance Dashboard 
*(Tableau + TabPy + Claude LLM)*

## Overview
Healthcare quality data is complex, fragmented, and difficult for decision-makers to interpret quickly. This project solves that problem by embedding an **LLM-generated executive performance summary directly inside a Tableau dashboard**, transforming raw CMS hospital metrics into **clear, actionable insights**.

The solution demonstrates how **Large Language Models (LLMs)** can be responsibly integrated into business analytics workflows to enhance decision-making without replacing traditional BI tools.

---

## Business Problem
Hospital leadership and analytics teams often face:

- **Metric Overload:** Dozens of quality metrics spread across multiple dashboards.
- **Narrative Gap:** Difficulty translating metric movements into executive-level narratives.
- **Resource Drain:** Time-intensive manual interpretation during reviews and meetings.
- **Inconsistency:** Variations in storytelling across different facilities and analysts.

---

## Solution
This project integrates **Claude (Anthropic LLM)** with **Tableau via TabPy** to automatically generate a **one-screen, executive-ready hospital performance summary** for any selected facility.



**The AI summary:**
- Interprets performance across CMS quality domains.
- Aligns insights with the visuals already shown in Tableau.
- Highlights strengths, risks, and priority focus areas.
- Uses strict data-only prompting to prevent hallucinations.

---

## Key Features
- **Embedded AI:** LLM-powered executive summary inside the Tableau interface.
- **Fuzzy Matching:** Hospital-level filtering with resilient facility name resolution.
- **Directional Logic:** Metric-aware interpretation (recognizing where "lower is better," e.g., mortality rates).
- **CMS Alignment:** Uses standardized healthcare quality terminology.
- **Governance-First:** Designed with guardrails to ensure no speculation or assumptions.

---

## Impact & Use Cases

### Business Impact
- **Efficiency:** Reduces time required to interpret complex hospital quality dashboards.
- **Standardization:** Harmonizes performance narratives across the entire organization.
- **Clarity:** Enhances executive understanding without requiring extra analyst intervention.
- **Innovation:** Serves as a blueprint for responsible AI adoption in healthcare BI.

### Real-World Use Cases
- Hospital executive performance reviews.
- Quality improvement (QI) committee meetings.
- Board-level reporting and state-of-the-hospital summaries.
- Analyst productivity acceleration.

---

## Dashboard Coverage
The AI summary and dashboard analyze hospital performance across:

- **Emergency Department:** Flow, access, and wait times.
- **Sepsis Care:** Timeliness and adherence to protocols.
- **Readmissions:** Performance against predicted vs. expected rates.
- **Safety:** Mortality, complications, and healthcare-associated infections (HAIs).
- **Patient Experience:** HCAHPS scores and patient satisfaction metrics.

---

## Data Source
All data used in this project is sourced from **CMS Hospital Compare** datasets.
[https://data.cms.gov/provider-data/topics/hospitals](https://data.cms.gov/provider-data/topics/hospitals)

*Note: No data is altered or synthesized. The AI summary is strictly constrained to the metrics provided within the data context.*

---

## AI Governance & Design Principles
To ensure trust and clinical reliability:
- **Data Grounding:** Uses only the provided hospital data.
- **No Hallucinations:** No external web browsing or external knowledge assumptions.
- **Objective Reporting:** No causal claims or speculative "why" statements without data.
- **Tone Control:** Executive, professional, and non-alarmist language.

---

## Setup Instructions

### Step 1: Install Dependencies
pip install -r requirements.txt

### Step 2: Set Environment Variable
Mac / Linux
export ANTHROPIC_API_KEY="your_api_key_here"
Windows
setx ANTHROPIC_API_KEY "your_api_key_here"

### Step 3: Start TabPy (Terminal 1)
Open a new terminal window and run: tabpy
TabPy will start on: http://localhost:9004

### Step 4: Deploy the Python Function (Terminal 2)
Open a second terminal window and run:
python deploy_claude_dashboard_summary.py
You should see: Deployed endpoint: claude_dashboard_summary

### Step 5: Open Tableau Dashboard
Open Tableau Desktop

Load the provided dashboard (Heathcare Dashboard with Claude.twbx)

Ensure TabPy is connected:

Help → Settings and Performance → Manage External Service Connection

Server: localhost

Port: 9004

Once connected, selecting a hospital in the dashboard will trigger the LLM-generated executive summary.
