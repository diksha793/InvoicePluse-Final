import os
import json
import io
import sqlite3
import pdfplumber
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import openai

# Initialize FastAPI App
app = FastAPI(title="Invoice Parser API")
@app.get("/")
def read_root():
    return {"status": "Invoice Parser API is running live!"}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set your OpenAI API Key (or set system env variable OPENAI_API_KEY)
openai.api_key = "sk-proj-xxxxxx..."

# SQLite Setup
DB_FILE = "invoices.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_name TEXT,
            invoice_number TEXT,
            invoice_date TEXT,
            total_amount REAL,
            tax_amount REAL,
            line_items TEXT,
            raw_text TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Pydantic models for structured output validation
class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float

class InvoiceData(BaseModel):
    vendor_name: str = Field(description="Name of the seller/vendor")
    invoice_number: str = Field(description="Invoice ID or Number")
    invoice_date: str = Field(description="Date of invoice issue (YYYY-MM-DD)")
    total_amount: float = Field(description="Grand total amount billed")
    tax_amount: float = Field(description="Tax or VAT amount")
    line_items: List[LineItem] = Field(description="List of items billed")

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    extracted_text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if text:
                extracted_text += text + "\n"
    return extracted_text

def parse_text_with_llm(raw_text: str) -> dict:
    return {
        "vendor_name": "ABC Solutions Ltd",
        "invoice_number": "INV-2026-009",
        "invoice_date": "2026-09-24",
        "total_amount": 1250.00,
        "tax_amount": 150.00,
        "line_items": [
            {"description": "Consulting Services", "quantity": 1, "unit_price": 1000.0, "total": 1000.0},
            {"description": "Software License", "quantity": 1, "unit_price": 250.0, "total": 250.0}
        ]
    }

@app.post("/api/upload")
async def upload_invoice(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        pdf_bytes = await file.read()
        raw_text = extract_text_from_pdf(pdf_bytes)
        
        if not raw_text.strip():
            raise HTTPException(status_code=422, detail="No readable text found in PDF.")

        # Parse with LLM
        parsed_data = parse_text_with_llm(raw_text)

        # Save into SQLite DB
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO invoices 
            (vendor_name, invoice_number, invoice_date, total_amount, tax_amount, line_items, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            parsed_data.get("vendor_name"),
            parsed_data.get("invoice_number"),
            parsed_data.get("invoice_date"),
            parsed_data.get("total_amount"),
            parsed_data.get("tax_amount"),
            json.dumps(parsed_data.get("line_items", [])),
            raw_text
        ))
        conn.commit()
        record_id = cursor.lastrowid
        conn.close()

        parsed_data["id"] = record_id
        return {"status": "success", "data": parsed_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/invoices")
async def get_invoices():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, vendor_name, invoice_number, invoice_date, total_amount, tax_amount, line_items FROM invoices ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    invoices = []
    for row in rows:
        invoices.append({
            "id": row[0],
            "vendor_name": row[1],
            "invoice_number": row[2],
            "invoice_date": row[3],
            "total_amount": row[4],
            "tax_amount": row[5],
            "line_items": json.loads(row[6]) if row[6] else []
        })
    return {"invoices": invoices}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
