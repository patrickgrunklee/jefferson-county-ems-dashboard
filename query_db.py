"""
Query helper for Jefferson County EMS Research Database
Run from command line: python query_db.py "your search term"
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / 'research_documents.db'

def search(query: str, limit: int = 10):
    """Full-text search across all documents."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('''
        SELECT d.file_name, cat.name as category, c.chunk_label,
               substr(c.content, 1, 500) as preview
        FROM content_fts fts
        JOIN content_chunks c ON fts.rowid = c.id
        JOIN documents d ON c.document_id = d.id
        JOIN categories cat ON d.category_id = cat.id
        WHERE content_fts MATCH ?
        LIMIT ?
    ''', (query, limit))

    results = cur.fetchall()
    conn.close()
    return results

def contracts_for(municipality: str):
    """Find all contracts mentioning a municipality."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('''
        SELECT d.file_name, d.contract_start_date, d.contract_end_date
        FROM documents d
        JOIN document_municipalities dm ON d.id = dm.document_id
        JOIN municipalities m ON dm.municipality_id = m.id
        JOIN categories cat ON d.category_id = cat.id
        WHERE (m.name LIKE ? OR m.short_name LIKE ?)
          AND cat.name = 'EMS Service Contract'
    ''', (f'%{municipality}%', f'%{municipality}%'))

    results = cur.fetchall()
    conn.close()
    return results

def list_municipalities():
    """List all municipalities in the database."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT name, municipality_type FROM municipalities ORDER BY name')
    results = cur.fetchall()
    conn.close()
    return results

def list_providers():
    """List all service providers."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT name, provider_type FROM service_providers ORDER BY name')
    results = cur.fetchall()
    conn.close()
    return results

def documents_by_category(category: str = None):
    """List documents, optionally filtered by category."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if category:
        cur.execute('''
            SELECT d.file_name, cat.name, d.file_type
            FROM documents d
            JOIN categories cat ON d.category_id = cat.id
            WHERE cat.name LIKE ?
            ORDER BY cat.name, d.file_name
        ''', (f'%{category}%',))
    else:
        cur.execute('''
            SELECT d.file_name, cat.name, d.file_type
            FROM documents d
            JOIN categories cat ON d.category_id = cat.id
            ORDER BY cat.name, d.file_name
        ''')

    results = cur.fetchall()
    conn.close()
    return results

def get_document_content(filename: str):
    """Get full content of a specific document."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('''
        SELECT c.chunk_label, c.content
        FROM content_chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.file_name LIKE ?
        ORDER BY c.chunk_index
    ''', (f'%{filename}%',))

    results = cur.fetchall()
    conn.close()
    return results

if __name__ == '__main__':
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        print(f"Searching for: {query}\n")
        for r in search(query):
            print(f"[{r[1]}] {r[0]} - {r[2]}")
            print(f"  {r[3][:200]}...\n")
    else:
        print("Usage: python query_db.py <search terms>")
