"""
Enterprise AI Knowledge Assistant - Backend Application
=====================================================
A Flask-based REST API for managing documents in a ChromaDB vector database.
Supports CRUD operations, file uploads, and text extraction from multiple file formats.

Author: Abigail Lenihan
Final Year Project - University College Cork
"""

# ========================================
# IMPORTS
# ========================================
from flask import Flask, jsonify, request, render_template, Response
import chromadb
import uuid
import PyPDF2
from docx import Document
from pptx import Presentation
import openpyxl
from bs4 import BeautifulSoup
import io
from datetime import datetime

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

# Define supported file types and their extraction functions
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

# Initialize ChromaDB persistent client
# Using a separate folder to avoid cache issues
chroma_client = chromadb.PersistentClient(path="./chroma_data_v2")

# Create or get the collection with no embedding function
# Note: embedding_function=None prevents ChromaDB from downloading models
collection = chroma_client.get_or_create_collection(
    name="synthetic_docs_v2",
    embedding_function=None
)


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
    existing_docs = collection.get()
    if existing_docs['metadatas']:
        for metadata in existing_docs['metadatas']:
            if metadata.get('name') == document_name:
                return jsonify({
                    "status": "duplicate",
                    "message": f"A document with the name '{document_name}' already exists.",
                    "existing_id": existing_docs['ids'][existing_docs['metadatas'].index(metadata)]
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
            extractor = file_extractors[file_ext]
            
            if file_ext in ['.txt', '.csv', '.json', '.md', '.log']:
                # Text files - decode as UTF-8
                content_to_store = extractor(file_content)
            else:
                # Binary files - pass bytes to extractor
                content_to_store = extractor(file_content)
            
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
    
    # Generate dummy embedding vector (prevents ChromaDB from downloading models)
    dummy_vector = [[0.1] * 384]
    
    # Generate unique document ID
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    
    # Insert document into ChromaDB
    collection.upsert(
        documents=[content_to_store],
        embeddings=dummy_vector,
        metadatas=[{
            "name": document_name,
            "category": document_category,
            "confidentiality": "Internal",
            "source": source,
            "created_at": datetime.now().isoformat()
        }],
        ids=[doc_id]
    )
    
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
        results = collection.get()
        categories = set()
        
        if results['metadatas']:
            for metadata in results['metadatas']:
                if 'category' in metadata:
                    categories.add(metadata['category'])
        
        return jsonify({
            "status": "success",
            "categories": sorted(list(categories))
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
        results = collection.get()
        documents = []
        
        if results['documents']:
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results['metadatas'] and i < len(results['metadatas']) else {}
                doc_id = results['ids'][i] if results['ids'] and i < len(results['ids']) else f"doc_{i}"
                
                documents.append({
                    "id": doc_id,
                    "content": doc,
                    "name": metadata.get('name', 'Untitled'),
                    "source": metadata.get('source', 'Unknown'),
                    "category": metadata.get('category', 'Uncategorized'),
                    "created_at": metadata.get('created_at'),
                    "updated_at": metadata.get('updated_at')
                })
        
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
        results = collection.get(ids=[doc_id])
        
        if not results['documents'] or len(results['documents']) == 0:
            return "Document not found", 404
        
        document_content = results['documents'][0]
        metadata = results['metadatas'][0] if results['metadatas'] and len(results['metadatas']) > 0 else {}
        source = metadata.get('source', 'Unknown')
        
        # Extract filename from source if it's a file
        if source.startswith('File:'):
            filename = source.replace('File: ', '')
        else:
            filename = f"{doc_id}.txt"
        
        # Return as downloadable file
        response = Response(document_content, mimetype='text/plain')
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
        
        # Check if document exists
        existing = collection.get(ids=[doc_id])
        if not existing['documents'] or len(existing['documents']) == 0:
            return jsonify({"status": "error", "message": "Document not found."}), 404
        
        # Get existing metadata and update it
        metadata = existing['metadatas'][0] if existing['metadatas'] and len(existing['metadatas']) > 0 else {}
        metadata['updated'] = "true"
        metadata['updated_at'] = datetime.now().isoformat()
        # Only update name if a new one is provided, otherwise keep existing
        if new_name:
            metadata['name'] = new_name
        # Category is mandatory, always update
        metadata['category'] = new_category
        
        # Update the document in ChromaDB
        dummy_vector = [[0.1] * 384]
        collection.update(
            ids=[doc_id],
            documents=[new_content],
            embeddings=dummy_vector,
            metadatas=[metadata]
        )
        
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
        collection.delete(ids=[doc_id])
        return jsonify({
            "status": "success",
            "message": f"Document {doc_id} deleted successfully."
        })
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
        JSON response with collection info and formatted document data
    """
    try:
        # Get collection statistics
        count = collection.count()
        
        # Get all documents
        results = collection.get()
        
        # Format documents with metadata for easier debugging
        formatted_docs = []
        if results['documents']:
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results['metadatas'] and i < len(results['metadatas']) else {}
                formatted_docs.append({
                    "id": results['ids'][i] if results['ids'] and i < len(results['ids']) else f"doc_{i}",
                    "name": metadata.get('name', 'Untitled'),
                    "category": metadata.get('category', 'Uncategorized'),
                    "source": metadata.get('source', 'Unknown'),
                    "created_at": metadata.get('created_at'),
                    "updated_at": metadata.get('updated_at'),
                    "content_preview": doc[:100] if len(doc) > 100 else doc,
                    "content_length": len(doc)
                })
        
        debug_info = {
            "collection_name": collection.name,
            "document_count": count,
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
