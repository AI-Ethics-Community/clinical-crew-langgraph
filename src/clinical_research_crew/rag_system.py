"""RAG (Retrieval-Augmented Generation) system for medical knowledge bases.

This module provides document loading, embedding, vector storage, and retrieval
functionality for specialty-specific medical knowledge bases.
"""

import hashlib
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Specialty definitions
SPECIALTIES = [
    "cardiology",
    "pharmacology",
    "neurology",
    "emergency",
    "gynecology",
    "internal_medicine",
    "surgery",
    "nutrition",
    "prevention",
    "epidemiology",
]


class MedicalKnowledgeBase:
    """Medical knowledge base with RAG capabilities for a specific specialty.
    
    This class handles document loading, chunking, embedding, and retrieval
    for a single medical specialty.
    """
    
    def __init__(
        self,
        specialty: str,
        knowledge_base_path: str = "./knowledge_bases",
        embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        vector_store_path: str = "./vector_stores",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        """Initialize medical knowledge base for a specialty.
        
        Args:
            specialty: Medical specialty name
            knowledge_base_path: Root path for knowledge base documents
            embeddings_model: HuggingFace embeddings model name
            vector_store_path: Path to store vector indices
            chunk_size: Size of text chunks for embedding
            chunk_overlap: Overlap between chunks
        """
        if specialty not in SPECIALTIES:
            raise ValueError(f"Invalid specialty: {specialty}. Must be one of {SPECIALTIES}")
        
        self.specialty = specialty
        self.knowledge_base_path = Path(knowledge_base_path) / specialty
        self.vector_store_path = Path(vector_store_path) / specialty
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Create directories if they don't exist
        self.knowledge_base_path.mkdir(parents=True, exist_ok=True)
        self.vector_store_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize embeddings
        logger.info(f"Loading embeddings model: {embeddings_model}")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=embeddings_model,
            model_kwargs={"device": "cpu"},  # Change to "cuda" if GPU available
            encode_kwargs={"normalize_embeddings": True}
        )
        
        # Initialize or load vector store
        self.vector_store = self._load_or_create_vector_store()
        
        # Cache for frequently accessed documents
        self._cache: Dict[str, List[Document]] = {}
    
    def _load_or_create_vector_store(self) -> Chroma:
        """Load existing vector store or create new one.
        
        Returns:
            Chroma vector store instance
        """
        try:
            if (self.vector_store_path / "chroma.sqlite3").exists():
                logger.info(f"Loading existing vector store for {self.specialty}")
                return Chroma(
                    persist_directory=str(self.vector_store_path),
                    embedding_function=self.embeddings
                )
            else:
                logger.info(f"Creating new vector store for {self.specialty}")
                return Chroma(
                    persist_directory=str(self.vector_store_path),
                    embedding_function=self.embeddings
                )
        except Exception as e:
            logger.error(f"Error loading vector store: {e}")
            return Chroma(
                persist_directory=str(self.vector_store_path),
                embedding_function=self.embeddings
            )
    
    def load_document(self, file_path: Path) -> List[Document]:
        """Load a single document based on its file type.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            List of Document objects
        """
        suffix = file_path.suffix.lower()
        
        try:
            if suffix == ".pdf":
                loader = PyPDFLoader(str(file_path))
            elif suffix in [".doc", ".docx"]:
                loader = UnstructuredWordDocumentLoader(str(file_path))
            elif suffix == ".md":
                loader = UnstructuredMarkdownLoader(str(file_path))
            elif suffix == ".txt":
                loader = TextLoader(str(file_path))
            else:
                logger.warning(f"Unsupported file type: {suffix}")
                return []
            
            documents = loader.load()
            
            # Add metadata
            for doc in documents:
                doc.metadata.update({
                    "specialty": self.specialty,
                    "source_file": str(file_path.name),
                    "file_type": suffix,
                })
                
                # Extract metadata from filename if following convention
                # Format: YYYY_SOURCE_TOPIC_VERSION.ext
                parts = file_path.stem.split("_")
                if len(parts) >= 3 and parts[0].isdigit():
                    doc.metadata.update({
                        "year": parts[0],
                        "source": parts[1],
                        "topic": "_".join(parts[2:]),
                    })
            
            logger.info(f"Loaded {len(documents)} document(s) from {file_path.name}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return []
    
    def load_all_documents(self) -> List[Document]:
        """Load all documents from the specialty knowledge base.
        
        Returns:
            List of all Document objects
        """
        all_documents = []
        supported_extensions = [".pdf", ".docx", ".doc", ".txt", ".md"]
        
        for file_path in self.knowledge_base_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                documents = self.load_document(file_path)
                all_documents.extend(documents)
        
        logger.info(f"Loaded total of {len(all_documents)} documents for {self.specialty}")
        return all_documents
    
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks for embedding.
        
        Args:
            documents: List of Document objects
            
        Returns:
            List of chunked Document objects
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        chunked_docs = text_splitter.split_documents(documents)
        logger.info(f"Created {len(chunked_docs)} chunks from {len(documents)} documents")
        
        return chunked_docs
    
    def index_documents(self, documents: Optional[List[Document]] = None) -> None:
        """Index documents into the vector store.
        
        Args:
            documents: Optional list of documents to index. If None, loads all documents.
        """
        if documents is None:
            documents = self.load_all_documents()
        
        if not documents:
            logger.warning(f"No documents found for {self.specialty}")
            return
        
        # Chunk documents
        chunked_docs = self.chunk_documents(documents)
        
        # Add to vector store
        logger.info(f"Indexing {len(chunked_docs)} chunks for {self.specialty}")
        self.vector_store.add_documents(chunked_docs)
        self.vector_store.persist()
        
        logger.info(f"Successfully indexed documents for {self.specialty}")
    
    def add_document(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a single document to the knowledge base.
        
        Args:
            file_path: Path to the document file
            metadata: Optional additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            path = Path(file_path)
            
            # Copy file to knowledge base if not already there
            if not path.parent == self.knowledge_base_path:
                import shutil
                dest = self.knowledge_base_path / path.name
                shutil.copy(path, dest)
                path = dest
            
            # Load and index document
            documents = self.load_document(path)
            
            if metadata:
                for doc in documents:
                    doc.metadata.update(metadata)
            
            chunked_docs = self.chunk_documents(documents)
            self.vector_store.add_documents(chunked_docs)
            self.vector_store.persist()
            
            logger.info(f"Successfully added document: {path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding document: {e}")
            return False
    
    @lru_cache(maxsize=128)
    def _cached_query(self, query_hash: str, k: int) -> Tuple[str, ...]:
        """Internal cached query method.
        
        Args:
            query_hash: Hash of the query string
            k: Number of results
            
        Returns:
            Tuple of document page contents (for hashability)
        """
        # This is a placeholder - actual caching happens in query() method
        pass
    
    def query(
        self,
        query: str,
        k: int = 3,
        filter_dict: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> List[Document]:
        """Query the knowledge base for relevant documents.
        
        Args:
            query: Search query
            k: Number of documents to return
            filter_dict: Optional metadata filters
            use_cache: Whether to use cached results
            
        Returns:
            List of relevant Document objects with metadata
        """
        # Create cache key
        cache_key = hashlib.md5(f"{query}_{k}_{filter_dict}".encode()).hexdigest()
        
        # Check cache
        if use_cache and cache_key in self._cache:
            logger.info(f"Cache hit for query: {query[:50]}...")
            return self._cache[cache_key]
        
        # Perform similarity search
        try:
            if filter_dict:
                results = self.vector_store.similarity_search(
                    query,
                    k=k,
                    filter=filter_dict
                )
            else:
                results = self.vector_store.similarity_search(query, k=k)
            
            # Cache results
            if use_cache:
                self._cache[cache_key] = results
            
            logger.info(f"Found {len(results)} relevant documents for {self.specialty}")
            return results
            
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")
            return []
    
    def format_retrieved_docs(self, documents: List[Document]) -> str:
        """Format retrieved documents as a string for LLM context.
        
        Args:
            documents: List of retrieved Document objects
            
        Returns:
            Formatted string with document contents and metadata
        """
        if not documents:
            return "No relevant documents found in knowledge base."
        
        formatted_parts = []
        for i, doc in enumerate(documents, 1):
            metadata_str = ", ".join([
                f"{k}: {v}" for k, v in doc.metadata.items()
                if k not in ["embedding", "page"]  # Exclude large/irrelevant metadata
            ])
            
            formatted_parts.append(
                f"[Document {i}]\n"
                f"Metadata: {metadata_str}\n"
                f"Content:\n{doc.page_content}\n"
                f"{'='*80}\n"
            )
        
        return "\n".join(formatted_parts)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the knowledge base.
        
        Returns:
            Dictionary with statistics
        """
        try:
            collection = self.vector_store._collection
            doc_count = collection.count()
            
            # Count files in directory
            file_count = len([
                f for f in self.knowledge_base_path.rglob("*")
                if f.is_file() and f.suffix.lower() in [".pdf", ".docx", ".txt", ".md"]
            ])
            
            return {
                "specialty": self.specialty,
                "indexed_chunks": doc_count,
                "source_files": file_count,
                "vector_store_path": str(self.vector_store_path),
                "knowledge_base_path": str(self.knowledge_base_path),
            }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {
                "specialty": self.specialty,
                "error": str(e)
            }


class RAGSystem:
    """Main RAG system managing all specialty knowledge bases."""
    
    def __init__(
        self,
        knowledge_base_path: str = "./knowledge_bases",
        embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        vector_store_path: str = "./vector_stores",
    ):
        """Initialize RAG system for all specialties.
        
        Args:
            knowledge_base_path: Root path for all knowledge bases
            embeddings_model: HuggingFace embeddings model name
            vector_store_path: Root path for vector stores
        """
        self.knowledge_base_path = knowledge_base_path
        self.embeddings_model = embeddings_model
        self.vector_store_path = vector_store_path
        
        # Initialize knowledge bases for all specialties
        self.knowledge_bases: Dict[str, MedicalKnowledgeBase] = {}
        
        for specialty in SPECIALTIES:
            try:
                self.knowledge_bases[specialty] = MedicalKnowledgeBase(
                    specialty=specialty,
                    knowledge_base_path=knowledge_base_path,
                    embeddings_model=embeddings_model,
                    vector_store_path=vector_store_path,
                )
                logger.info(f"Initialized knowledge base for {specialty}")
            except Exception as e:
                logger.error(f"Error initializing {specialty} knowledge base: {e}")
    
    def query_specialty(
        self,
        specialty: str,
        query: str,
        k: int = 3,
        format_for_llm: bool = True
    ) -> str:
        """Query a specific specialty knowledge base.
        
        Args:
            specialty: Medical specialty to query
            query: Search query
            k: Number of documents to retrieve
            format_for_llm: Whether to format results for LLM consumption
            
        Returns:
            Retrieved documents (formatted or raw)
        """
        if specialty not in self.knowledge_bases:
            logger.error(f"Unknown specialty: {specialty}")
            return f"Error: Unknown specialty '{specialty}'"
        
        kb = self.knowledge_bases[specialty]
        documents = kb.query(query, k=k)
        
        if format_for_llm:
            return kb.format_retrieved_docs(documents)
        else:
            return documents
    
    def index_all_specialties(self) -> None:
        """Index all documents for all specialties."""
        logger.info("Starting indexing for all specialties")
        
        for specialty, kb in self.knowledge_bases.items():
            try:
                logger.info(f"Indexing {specialty}...")
                kb.index_documents()
            except Exception as e:
                logger.error(f"Error indexing {specialty}: {e}")
        
        logger.info("Completed indexing for all specialties")
    
    def get_all_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all specialty knowledge bases.
        
        Returns:
            Dictionary mapping specialty to statistics
        """
        return {
            specialty: kb.get_statistics()
            for specialty, kb in self.knowledge_bases.items()
        }


# Convenience functions

def get_rag_system(
    knowledge_base_path: Optional[str] = None,
    embeddings_model: Optional[str] = None
) -> RAGSystem:
    """Get or create RAG system instance.
    
    Args:
        knowledge_base_path: Optional custom knowledge base path
        embeddings_model: Optional custom embeddings model
        
    Returns:
        RAGSystem instance
    """
    kb_path = knowledge_base_path or os.getenv("KNOWLEDGE_BASE_PATH", "./knowledge_bases")
    emb_model = embeddings_model or os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    
    return RAGSystem(
        knowledge_base_path=kb_path,
        embeddings_model=emb_model
    )


def query_knowledge_base(specialty: str, query: str, top_k: int = 3) -> str:
    """Quick function to query a knowledge base.
    
    Args:
        specialty: Medical specialty
        query: Search query
        top_k: Number of results
        
    Returns:
        Formatted retrieved documents
    """
    rag_system = get_rag_system()
    return rag_system.query_specialty(specialty, query, k=top_k)
