#!/usr/bin/env python3
"""
PDF Reader MCP Server

A Model Context Protocol (MCP) server for extracting text content from PDF files with
comprehensive error handling, encoding detection, and standardised JSON output.

Features:
- Text extraction from PDF files using PyPDF2
- Error handling for corrupt, encrypted, or invalid PDFs
- Standardized JSON output format with detailed metadata

Author: Ola Tarkowska
Email: ola@entrypoint.tech

"""


import os
import logging
import asyncio
from typing import Dict, Any
from pathlib import Path

import PyPDF2
from fastmcp import FastMCP


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


mcp = FastMCP("pdf-reader")


def _create_error_response(error: str, message: str) -> Dict[str, Any]:
    """Create a standardized error response."""
    return {
        "success": False,
        "error": error,
        "message": message
    }


def extract_text_from_pdf(file_path: str) -> Dict[str, Any]:
    """
    Extract text from PDF with comprehensive error handling.
    """
    try:
        with open(file_path, 'rb') as pdf_file:
            # Create PDF reader
            try:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
            except PyPDF2.errors.PdfReadError as e:
                return _create_error_response(
                    "PDF_READ_ERROR",
                    f"Could not read PDF file: {str(e)}"
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                return _create_error_response(
                    "UNKNOWN_PDF_ERROR",
                    f"Unexpected error reading PDF: {str(e)}"
                )

            # Check if PDF is encrypted
            if pdf_reader.is_encrypted:
                return _create_error_response(
                    "PDF_ENCRYPTED",
                    "PDF file is encrypted and requires a password"
                )

            # Get basic PDF info
            num_pages = len(pdf_reader.pages)
            metadata = pdf_reader.metadata or {}

            # Extract text from all pages
            text_content = ""
            extracted_pages = 0

            for page_num, page in enumerate(pdf_reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_content += f"--- Page {page_num} ---\n{page_text}\n\n"
                        extracted_pages += 1
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning(
                        "Could not extract text from page %s: %s", page_num, e
                    )
                    text_content += (
                        f"--- Page {page_num} ---\n"
                        "[Error extracting text from this page]\n\n"
                    )

            # Clean up the text
            text_content = text_content.strip()

            return {
                "success": True,
                "data": {
                    "text": text_content,
                    "page_count": num_pages,
                    "pages_extracted": extracted_pages,
                    "metadata": {
                        "title": metadata.get("/Title", "Unknown"),
                        "author": metadata.get("/Author", "Unknown"),
                        "subject": metadata.get("/Subject", "Unknown"),
                        "creator": metadata.get("/Creator", "Unknown"),
                        "producer": metadata.get("/Producer", "Unknown"),
                        "creation_date": str(metadata.get("/CreationDate", "Unknown")),
                        "modification_date": str(metadata.get("/ModDate", "Unknown"))
                    }
                }
            }

    except (FileNotFoundError, PermissionError) as e:
        error_type = "FILE_NOT_FOUND" if isinstance(e, FileNotFoundError) else "PERMISSION_DENIED"
        error_msg = f"File not found: {file_path}" if isinstance(e, FileNotFoundError) \
                    else f"Permission denied accessing: {file_path}"
        return _create_error_response(error_type, error_msg)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Unexpected error processing PDF %s: %s", file_path, e)
        return _create_error_response(
            "UNEXPECTED_ERROR",
            f"Unexpected error: {str(e)}"
        )


@mcp.tool()
async def read_local_pdf(path: str) -> Dict[str, Any]:
    """
    Read and extract text content from a local PDF file.

    Args:
        path: Absolute or relative path to the PDF file

    Returns:
        Dictionary with success status, extracted text, and metadata
    """
    logger.info("Attempting to read PDF: %s", path)

    # Convert to absolute path for consistency
    abs_path = os.path.abspath(path)
    logger.info("Resolved absolute path: %s", abs_path)

    # Extract text
    result = extract_text_from_pdf(abs_path)

    if result["success"]:
        logger.info("Successfully extracted text from PDF: %s", abs_path)
        logger.info(
            "Pages: %s, Characters: %s",
            result['data']['page_count'],
            len(result['data']['text'])
        )
    else:
        logger.error("Failed to extract text from PDF: %s", result['message'])

    return result


@mcp.tool()
async def list_pdf_files(directory: str = ".") -> Dict[str, Any]:
    """
    List all PDF files in a given directory.

    Args:
        directory: Directory path to search for PDFs (default: current directory)

    Returns:
        Dictionary with list of PDF files and their basic info
    """
    try:
        dir_path = Path(directory).resolve()

        if not dir_path.exists():
            return {
                "success": False,
                "error": "DIRECTORY_NOT_FOUND",
                "message": f"Directory does not exist: {directory}"
            }

        if not dir_path.is_dir():
            return {
                "success": False,
                "error": "NOT_A_DIRECTORY",
                "message": f"Path is not a directory: {directory}"
            }

        pdf_files = []
        for pdf_path in dir_path.glob("**/*.pdf"):
            try:
                stat = pdf_path.stat()
                pdf_files.append({
                    "name": pdf_path.name,
                    "path": str(pdf_path),
                    "size_bytes": stat.st_size,
                    "modified": stat.st_mtime
                })
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Could not get info for %s: %s", pdf_path, e)

        return {
            "success": True,
            "data": {
                "directory": str(dir_path),
                "pdf_count": len(pdf_files),
                "files": sorted(pdf_files, key=lambda x: x["name"])
            }
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        return {
            "success": False,
            "error": "DIRECTORY_ACCESS_ERROR",
            "message": f"Error accessing directory: {str(e)}"
        }


async def main():
    """
    Start the MCP server with HTTP transport.
    """
    logger.info("Starting PDF Reader MCP Server on port 8000...")
    logger.info("Available tools:")
    logger.info(" - read_local_pdf: Extract text from a PDF file")
    logger.info(" - list_pdf_files: List PDF files in a directory")

    try:
        await mcp.run_async()
    except Exception as e:
        logger.error("Server failed to start: %s", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
