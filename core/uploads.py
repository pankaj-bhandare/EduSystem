"""validateUploadedFile() equivalent: check the file's real content, not its name or browser MIME."""
import uuid
import zipfile

from django import forms

SIGNATURES = {
    "pdf": lambda h, f: h.startswith(b"%PDF-"),
    "png": lambda h, f: h.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpg": lambda h, f: h.startswith(b"\xff\xd8\xff"),
    "ppt": lambda h, f: h.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    "pptx": lambda h, f: h.startswith(b"PK\x03\x04") and _is_pptx(f),
}


def _is_pptx(f):
    try:
        f.seek(0)
        with zipfile.ZipFile(f) as z:
            return any(n.startswith("ppt/") for n in z.namelist())
    except zipfile.BadZipFile:
        return False


def clean_upload(upload, allowed, max_mb=10):
    """Validate by content, rename to a random name, return the file. `allowed` = {'pdf','png',...}."""
    if upload.size < 1 or upload.size > max_mb * 1024 * 1024:
        raise forms.ValidationError(f"The file is empty or larger than {max_mb} MB.")
    upload.seek(0)
    head = upload.read(16)
    kind = next((k for k in allowed if SIGNATURES[k](head, upload)), None)
    upload.seek(0)
    if kind is None:
        raise forms.ValidationError("This file type is not allowed.")
    upload.name = f"{uuid.uuid4().hex}.{kind}"
    return upload
