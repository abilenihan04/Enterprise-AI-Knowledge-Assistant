"""
Enterprise AI Knowledge Assistant - Backend Application
=====================================================
A Flask-based REST API for managing documents stored in a PostgreSQL database.
Supports CRUD operations, file uploads, and text extraction from multiple file formats,
plus natural language search (search.py) and AI-written answers (answers.py).

Author: Abigail Lenihan
Final Year Project - University College Cork
"""

# ========================================
# IMPORTS
# ========================================
from flask import Flask, jsonify, request, render_template, Response
from psycopg.errors import UniqueViolation
import uuid
import PyPDF2
from docx import Document
from pptx import Presentation
import openpyxl
from bs4 import BeautifulSoup
import io

# Project modules: database connection, search/indexing, and answer generation
from db import pool, init_db
from search import build_chunks, save_chunks, search_documents
from answers import generate_answer, AnswerUnavailable

# ========================================
# FILE EXTRACTION FUNCTIONS
# ========================================

def extract_text_from_pdf(file_content):
    """
    Extract text content from a PDF file.
    
    Args:
        file_content (bytes): Raw PDF file content
        
    Returns:
        str: Extracted text from all pages
    """
    # io.BytesIO lets the library read the uploaded bytes as if they were a file on disk
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    return text


def extract_text_from_docx(file_content):
    """
    Extract text content from a Word document (.docx).
    
    Args:
        file_content (bytes): Raw Word document content
        
    Returns:
        str: Extracted text from all paragraphs
    """
    doc = Document(io.BytesIO(file_content))
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text


def extract_text_from_pptx(file_content):
    """
    Extract text content from a PowerPoint presentation (.pptx).
    
    Args:
        file_content (bytes): Raw PowerPoint content
        
    Returns:
        str: Extracted text from all slides and shapes
    """
    prs = Presentation(io.BytesIO(file_content))
    text = ""
    for slide in prs.slides:
        for shape in slide.shapes:
            # Only some shapes (text boxes, titles) contain text; pictures etc. are skipped
            if hasattr(shape, "text"):
                text += shape.text + "\n"
    return text


def extract_text_from_xlsx(file_content):
    """
    Extract text content from an Excel spreadsheet (.xlsx).
    
    Args:
        file_content (bytes): Raw Excel file content
        
    Returns:
        str: Extracted text from all cells in all sheets
    """
    workbook = openpyxl.load_workbook(io.BytesIO(file_content))
    text = ""
    for sheet in workbook:
        for row in sheet.iter_rows(values_only=True):
            # Join the cells of each row with spaces; empty cells become empty strings
            row_text = " ".join([str(cell) if cell is not None else "" for cell in row])
            if row_text.strip():
                text += row_text + "\n"
    return text


def extract_text_from_html(file_content):
    """
    Extract text content from an HTML file.
    
    Args:
        file_content (bytes): Raw HTML content
        
    Returns:
        str: Extracted text without HTML tags
    """
    soup = BeautifulSoup(file_content, 'html.parser')
    return soup.get_text(separator='\n', strip=True)


def extract_text_from_epub(file_content):
    """
    Extract text content from an EPUB file.
    
    Args:
        file_content (bytes): Raw EPUB file content
        
    Returns:
        str: Extracted text from all chapters
    """
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
        import zipfile
        import os
        
        # Try ebooklib first
        try:
            book = epub.read_epub(io.BytesIO(file_content))
            text = ""
            
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    try:
                        # Parse HTML content from EPUB
                        html_content = item.get_content()
                        if html_content:
                            soup = BeautifulSoup(html_content, 'html.parser')
                            extracted = soup.get_text(separator='\n', strip=True)
                            if extracted:
                                text += extracted + "\n"
                    except Exception:
                        # Skip items that fail to parse
                        continue
            
            if text:
                return text
        except Exception:
            # Fall back to manual extraction if ebooklib fails
            pass
        
        # Fallback: Treat EPUB as ZIP and extract HTML files
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as zip_ref:
                text = ""
                for file_info in zip_ref.filelist:
                    if file_info.filename.endswith('.html') or file_info.filename.endswith('.xhtml'):
                        try:
                            html_content = zip_ref.read(file_info.filename)
                            if html_content:
                                soup = BeautifulSoup(html_content, 'html.parser')
                                extracted = soup.get_text(separator='\n', strip=True)
                                if extracted:
                                    text += extracted + "\n"
                        except Exception:
                            continue
                return text if text else "No text content found in EPUB file"
        except Exception as e:
            raise Exception(f"Could not extract text from EPUB file: {str(e)}")
            
    except ImportError:
        raise Exception("ebooklib library is required for EPUB support. Install with: pip install EbookLib")
    except Exception as e:
        raise Exception(f"Error processing EPUB file: {str(e)}")


# ========================================
# FILE TYPE EXTRACTORS CONFIGURATION
# ========================================

# Define supported file types and their extraction functions.
# Each maps a file extension to a function that takes the raw file bytes and returns text.
# Plain text formats just need decoding; the rest use the extractors above.
FILE_EXTRACTORS = {
    '.txt': lambda x: x.decode('utf-8'),
    '.csv': lambda x: x.decode('utf-8'),
    '.json': lambda x: x.decode('utf-8'),
    '.md': lambda x: x.decode('utf-8'),
    '.log': lambda x: x.decode('utf-8'),
    '.pdf': extract_text_from_pdf,
    '.docx': extract_text_from_docx,
    '.pptx': extract_text_from_pptx,
    '.xlsx': extract_text_from_xlsx,
    '.html': lambda x: extract_text_from_html(x),
    '.htm': lambda x: extract_text_from_html(x),
    '.epub': extract_text_from_epub,
}


# ========================================
# FLASK APPLICATION SETUP
# ========================================

# Initialize Flask app with template folder configuration
app = Flask(__name__, template_folder='templates')

# Connect to PostgreSQL and create the tables if they don't exist
init_db()


def to_iso(value):
    """Convert a database timestamp to an ISO 8601 string for JSON (None if missing)."""
    return value.isoformat() if value else None


def clean_text(text):
    """Remove NUL characters (found in some PDFs), which PostgreSQL text columns cannot store."""
    return text.replace('\x00', '')


# ========================================
# ROUTE: HOME PAGE
# ========================================

@app.route('/', methods=['GET'])
def home():
    """
    Serve the home page (knowledge base management interface).
    
    Returns:
        str: Rendered HTML template
    """
    return render_template('home.html')


# ========================================
# ROUTE: DOCUMENTS PAGE
# ========================================

@app.route('/documents', methods=['GET'])
def documents():
    """
    Serve the documents page (view all documents interface).
    
    Returns:
        str: Rendered HTML template
    """
    return render_template('documents.html')


# ========================================
# ROUTE: INSERT DOCUMENT
# ========================================

@app.route('/insert', methods=['POST'])
def insert_document():
    """
    Insert a new document into the knowledge base.
    
    Accepts either text input or file upload. Supports multiple file formats
    including PDF, DOCX, PPTX, XLSX, HTML, and plain text files.
    
    Required fields:
        - document_name: Name of the document
        - document_category: Category for classification
        
    Optional fields:
        - document_text: Plain text content
        - document_file: File upload
        
    Returns:
        JSON response with status and message
    """
    # Get form data
    document_text = request.form.get('document_text')
    document_name = request.form.get('document_name', '').strip()
    document_category = request.form.get('document_category', '').strip()
    
    # Check if a file was uploaded
    document_file = request.files.get('document_file')
    
    # If no document name provided, use filename
    if not document_name and document_file and document_file.filename:
        document_name = document_file.filename.rsplit('.', 1)[0]  # Remove extension
    
    # Validate mandatory fields
    if not document_name:
        return jsonify({"status": "error", "message": "Document name is required (or upload a file)."}), 400
    
    if not document_category:
        return jsonify({"status": "error", "message": "Category is required."}), 400
    
    # Check for duplicate document name
    with pool.connection() as conn:
        existing = conn.execute(
            "SELECT id FROM documents WHERE name = %s", (document_name,)
        ).fetchone()
    if existing:
        return jsonify({
            "status": "duplicate",
            "message": f"A document with the name '{document_name}' already exists.",
            "existing_id": existing['id']
        }), 409
    
    # Use the global file extractors configuration
    file_extractors = FILE_EXTRACTORS
    
    # Process file upload or text input
    if document_file and document_file.filename:
        # Check file extension
        file_ext = '.' + document_file.filename.rsplit('.', 1)[1].lower() if '.' in document_file.filename else ''
        
        if file_ext not in file_extractors:
            return jsonify({
                "status": "error", 
                "message": f"File type not supported. Supported types: {', '.join(file_extractors.keys())}"
            }), 400
        
        # Extract text from file
        try:
            file_content = document_file.read()
            content_to_store = file_extractors[file_ext](file_content)
            source = f"File: {document_file.filename}"
        except Exception as e:
            return jsonify({
                "status": "error", 
                "message": f"Unable to process file: {str(e)}"
            }), 400
    elif document_text:
        content_to_store = document_text
        source = "Text input"
    else:
        return jsonify({"status": "error", "message": "Please provide either text or a file."}), 400
    
    content_to_store = clean_text(content_to_store)
    # Split the text into chunks and embed them for search. This is done before opening the
    # database transaction, so the slow model work doesn't hold a connection open.
    chunks = build_chunks(content_to_store)
    
    # Generate unique document ID
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    
    # Insert document and its chunks into PostgreSQL in one transaction (created_at defaults to now())
    try:
        with pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO documents (id, name, category, confidentiality, source, content)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (doc_id, document_name, document_category, "Internal", source, content_to_store)
            )
            save_chunks(conn, doc_id, chunks)
    except UniqueViolation:
        # Another request inserted the same name between the duplicate check and this insert;
        # the UNIQUE constraint in schema.sql catches it
        return jsonify({
            "status": "error",
            "message": f"A document with the name '{document_name}' already exists."
        }), 409
    
    return jsonify({
        "status": "success", 
        "message": "Document successfully stored in knowledge base.", 
        "inserted_data": content_to_store, 
        "source": source
    })


# ========================================
# ROUTE: GET CATEGORIES
# ========================================

@app.route('/categories', methods=['GET'])
def get_categories():
    """
    Retrieve all unique categories from the knowledge base.
    
    Returns:
        JSON response with sorted list of categories
    """
    try:
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM documents ORDER BY category"
            ).fetchall()
        
        return jsonify({
            "status": "success",
            "categories": [row['category'] for row in rows]
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ========================================
# ROUTE: LIST ALL DOCUMENTS
# ========================================

@app.route('/list', methods=['GET'])
def list_documents():
    """
    Retrieve all documents from the knowledge base.
    
    Returns:
        JSON response with list of documents including metadata
    """
    try:
        with pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, source, category, content, created_at, updated_at
                FROM documents
                ORDER BY created_at NULLS FIRST, id
                """
            ).fetchall()
        
        documents = [{
            "id": row['id'],
            "content": row['content'],
            "name": row['name'],
            "source": row['source'],
            "category": row['category'],
            "created_at": to_iso(row['created_at']),
            "updated_at": to_iso(row['updated_at'])
        } for row in rows]
        
        return jsonify({
            "status": "success",
            "documents": documents,
            "count": len(documents)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ========================================
# ROUTE: DOWNLOAD DOCUMENT
# ========================================

@app.route('/download/<doc_id>', methods=['GET'])
def download_document(doc_id):
    """
    Download a document as a text file.
    
    Args:
        doc_id: Unique identifier of the document
        
    Returns:
        File download response with original filename (if available)
    """
    try:
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT content, source FROM documents WHERE id = %s", (doc_id,)
            ).fetchone()
        
        if not row:
            return "Document not found", 404
        
        source = row['source']
        
        # Extract filename from source if it's a file
        if source.startswith('File:'):
            filename = source.replace('File: ', '')
        else:
            filename = f"{doc_id}.txt"
        
        # Return as downloadable file
        response = Response(row['content'], mimetype='text/plain')
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return f"Error downloading document: {str(e)}", 500


# ========================================
# ROUTE: UPDATE DOCUMENT
# ========================================

@app.route('/update/<doc_id>', methods=['POST'])
def update_document(doc_id):
    """
    Update an existing document in the knowledge base.
    
    Args:
        doc_id: Unique identifier of the document to update
        
    Required fields:
        - document_text: New content for the document
        - document_name: Updated document name
        - document_category: Updated category
        
    Returns:
        JSON response with status and message
    """
    try:
        new_content = request.form.get('document_text')
        new_name = request.form.get('document_name', '').strip()
        new_category = request.form.get('document_category', '').strip()
        
        # Check if a file was uploaded
        document_file = request.files.get('document_file')
        
        # If file is uploaded, extract content from it
        if document_file and document_file.filename:
            file_ext = '.' + document_file.filename.rsplit('.', 1)[1].lower() if '.' in document_file.filename else ''
            
            # Use the global file extractors configuration
            file_extractors = FILE_EXTRACTORS
            
            if file_ext not in file_extractors:
                return jsonify({
                    "status": "error", 
                    "message": f"File type not supported. Supported types: {', '.join(file_extractors.keys())}"
                }), 400
            
            # Extract text from file
            try:
                file_content = document_file.read()
                new_content = file_extractors[file_ext](file_content)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Unable to process file: {str(e)}"}), 400
        
        # Validate required fields
        if not new_content:
            return jsonify({"status": "error", "message": "Please provide new content or upload a file."}), 400
        
        if not new_category:
            return jsonify({"status": "error", "message": "Category is required."}), 400
        
        new_content = clean_text(new_content)
        # Re-embed the new content so search reflects the updated text
        chunks = build_chunks(new_content)
        
        # Update the row. The name only changes if a new one is provided (COALESCE keeps the old one).
        try:
            with pool.connection() as conn:
                updated = conn.execute(
                    """
                    UPDATE documents
                    SET content = %s,
                        category = %s,
                        name = COALESCE(%s, name),
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (new_content, new_category, new_name or None, doc_id)
                ).fetchone()
                if updated:
                    save_chunks(conn, doc_id, chunks)
        except UniqueViolation:
            return jsonify({
                "status": "error",
                "message": f"A document with the name '{new_name}' already exists."
            }), 409
        
        if not updated:
            return jsonify({"status": "error", "message": "Document not found."}), 404
        
        return jsonify({
            "status": "success",
            "message": "Document updated successfully.",
            "updated_content": new_content
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ========================================
# ROUTE: DELETE DOCUMENT
# ========================================

@app.route('/delete/<doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """
    Delete a document from the knowledge base.
    
    Args:
        doc_id: Unique identifier of the document to delete
        
    Returns:
        JSON response with status and message
    """
    try:
        # RETURNING id tells us whether a row was actually deleted (None = no such document).
        # The document's chunks are removed automatically by ON DELETE CASCADE.
        with pool.connection() as conn:
            deleted = conn.execute(
                "DELETE FROM documents WHERE id = %s RETURNING id", (doc_id,)
            ).fetchone()
        
        if not deleted:
            return jsonify({"status": "error", "message": "Document not found."}), 404
        
        return jsonify({
            "status": "success",
            "message": f"Document {doc_id} deleted successfully."
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ========================================
# ROUTE: SEARCH PAGE
# ========================================

@app.route('/search', methods=['GET'])
def search():
    """
    Serve the search page (ask a question in plain English).
    
    Returns:
        str: Rendered HTML template
    """
    return render_template('search.html')


# ========================================
# ROUTE: NATURAL LANGUAGE QUERY
# ========================================

@app.route('/query', methods=['GET'])
def query_documents():
    """
    Find the documents that best match a plain-English question.
    
    Uses hybrid search (see search.py): semantic search with the local embedding model
    and pgvector, combined with PostgreSQL keyword search. Weak matches are left out.
    
    Query parameters:
        - q: The question, e.g. "how do I give feedback to users?"
        - category: (optional) only search documents in this category
        
    Returns:
        JSON response with the top matching documents, best first
    """
    question = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    if not question:
        return jsonify({"status": "error", "message": "Please enter a question."}), 400
    
    try:
        results = search_documents(question, category=category or None)
        return jsonify({"status": "success", "question": question, "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ========================================
# ROUTE: WRITTEN ANSWER
# ========================================

@app.route('/answer', methods=['GET'])
def answer_question():
    """
    Write a short answer to a plain-English question from the most relevant documents.
    
    Runs the same search as /query, then a local language model (Ollama, see answers.py)
    writes an answer using only the top passages. The sources returned are the passages
    closest in meaning to the answer, so the user can check it against the documents.
    
    Query parameters:
        - q: The question
        - category: (optional) only use documents in this category
        
    Returns:
        JSON response with the answer and the source documents it was based on
    """
    question = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    if not question:
        return jsonify({"status": "error", "message": "Please enter a question."}), 400
    
    try:
        results = search_documents(question, category=category or None)
        answer = generate_answer(question, results)
        return jsonify({"status": "success", "question": question, **answer})
    except AnswerUnavailable as e:
        # 503 = Service Unavailable: Ollama isn't running or the model isn't downloaded
        return jsonify({"status": "error", "message": str(e)}), 503
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ========================================
# ROUTE: DEBUG DATABASE
# ========================================

@app.route('/debug', methods=['GET'])
def debug_database():
    """
    Debug endpoint to inspect the database contents.
    
    Returns:
        JSON response with table info and formatted document data
    """
    try:
        with pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, category, source, created_at, updated_at,
                       LEFT(content, 100) AS content_preview,
                       LENGTH(content) AS content_length,
                       (SELECT COUNT(*) FROM document_chunks c WHERE c.document_id = documents.id) AS chunk_count
                FROM documents
                ORDER BY created_at NULLS FIRST, id
                """
            ).fetchall()
        
        formatted_docs = [{
            "id": row['id'],
            "name": row['name'],
            "category": row['category'],
            "source": row['source'],
            "created_at": to_iso(row['created_at']),
            "updated_at": to_iso(row['updated_at']),
            "content_preview": row['content_preview'],
            "content_length": row['content_length'],
            "chunk_count": row['chunk_count']
        } for row in rows]
        
        debug_info = {
            "database": "PostgreSQL",
            "table_name": "documents",
            "document_count": len(formatted_docs),
            "documents": formatted_docs
        }
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========================================
# MAIN ENTRY POINT
# ========================================

if __name__ == '__main__':
    # Run the Flask development server
    # Note: debug=True should not be used in production
    app.run(debug=True, port=5000)
