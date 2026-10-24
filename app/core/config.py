import os
import tempfile
from pathlib import Path


MAX_DXF_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES_PER_REQUEST = 20
UPLOAD_CHUNK_SIZE = 1024 * 1024
SAMPLE_DIR = Path(
    os.environ.get(
        "SAMPLE_DXF_DIR",
        str(Path(tempfile.gettempdir()) / "sariguzel-teklif" / "sample_dxf"),
    )
)
