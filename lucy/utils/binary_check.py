"""
Binary file detection.
"""

from __future__ import annotations

import os

# Known binary extensions
BINARY_EXTENSIONS = frozenset({
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.flac', '.ogg',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar', '.zst',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.exe', '.dll', '.so', '.dylib', '.a', '.o', '.obj',
    '.pyc', '.pyo', '.class', '.jar',
    '.wasm', '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.sqlite', '.db', '.sqlite3',
    '.bin', '.dat', '.iso', '.img',
    '.gguf', '.safetensors', '.pt', '.pth', '.onnx',
})

# Text extensions (override for ambiguous cases)
TEXT_EXTENSIONS = frozenset({
    '.txt', '.md', '.rst', '.csv', '.tsv', '.log',
    '.py', '.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs',
    '.java', '.c', '.h', '.cpp', '.cc', '.hpp', '.cs',
    '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala',
    '.html', '.css', '.scss', '.less', '.sass',
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.xml', '.sql', '.graphql', '.proto',
    '.sh', '.bash', '.zsh', '.fish', '.ps1',
    '.env', '.gitignore', '.dockerignore', '.editorconfig',
    '.lock', '.mod', '.sum',
    'Makefile', 'Dockerfile', 'Jenkinsfile', 'Vagrantfile',
})


def is_binary_file(path: str) -> bool:
    """Check if a file is binary."""
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    if ext in TEXT_EXTENSIONS:
        return False
    if ext in BINARY_EXTENSIONS:
        return True

    # Check file name (no extension)
    basename = os.path.basename(path)
    if basename in TEXT_EXTENSIONS:
        return False

    # Heuristic: read first 8KB and check for null bytes
    try:
        with open(path, 'rb') as f:
            chunk = f.read(8192)
        if b'\x00' in chunk:
            return True
        # Check if mostly printable
        text_chars = set(range(32, 127)) | {9, 10, 13}  # tab, newline, cr
        non_text = sum(1 for b in chunk if b not in text_chars)
        return non_text / max(len(chunk), 1) > 0.3
    except OSError:
        return True  # Can't read = treat as binary


def get_file_type(path: str) -> str:
    """Get human-readable file type."""
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    type_map = {
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
        '.jsx': 'JSX', '.tsx': 'TSX', '.java': 'Java',
        '.c': 'C', '.cpp': 'C++', '.h': 'C/C++ Header',
        '.go': 'Go', '.rs': 'Rust', '.rb': 'Ruby',
        '.php': 'PHP', '.swift': 'Swift', '.kt': 'Kotlin',
        '.html': 'HTML', '.css': 'CSS', '.json': 'JSON',
        '.yaml': 'YAML', '.yml': 'YAML', '.toml': 'TOML',
        '.md': 'Markdown', '.txt': 'Text', '.sh': 'Shell',
        '.sql': 'SQL', '.xml': 'XML', '.csv': 'CSV',
        '.png': 'PNG Image', '.jpg': 'JPEG Image',
        '.pdf': 'PDF', '.zip': 'ZIP Archive',
    }
    return type_map.get(ext, ext[1:].upper() if ext else 'Unknown')
